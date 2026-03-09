import json
import os
import re
import requests


# ── Field-type patterns for schema validation ─────────────────────────────────
FIELD_PATTERNS = {
    "phone":      re.compile(r"[\d\s\-\+\(\)\.]{7,20}"),
    "email":      re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"),
    "date":       re.compile(r"\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-]\d{2}[\/\-]\d{2}"),
    "id":         re.compile(r"[A-Z0-9\-]{3,}"),
}

FIELD_TYPE_HINTS = {
    "phone":  ["phone", "tel", "contact", "number"],
    "email":  ["email", "mail"],
    "date":   ["date", "time", "when", "dob"],
    "id":     ["id", "badge", "sid", "identifier", "emp"],
}


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None):
        """
        target_fields: dict or list containing the template field names to extract
        (dict format: {"field_name": "human_label"}, list format: ["field_name1", "field_name2"])
        """
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # dict or list
        self._json = json  # dictionary
        self._validation_warnings = []  # list of validation issues found

    def type_check_all(self):
        if type(self._transcript_text) is not str:
            raise TypeError(
                f"ERROR in LLM() attributes ->\
                Transcript must be text. Input:\n\ttranscript_text: {self._transcript_text}"
            )
        if not isinstance(self._target_fields, (list, dict)):
            raise TypeError(
                f"ERROR in LLM() attributes ->\
                Target fields must be a list or dict. Input:\n\ttarget_fields: {self._target_fields}"
            )

    def validate_extracted_fields(self) -> list:
        """
        Schema validation — checks extracted values match expected field types.

        Validates:
        - Phone numbers contain digits in expected format
        - Emails contain @ and a domain
        - Dates match common date patterns
        - No field value exceeds 500 chars (hallucination indicator)
        - No field is suspiciously repeated across multiple fields

        Returns a list of warning strings. Empty list = all valid.
        Never raises — validation issues are warnings, not hard failures.

        Closes Issue #114.
        """
        warnings = []
        values_seen = {}  # track repeated values across fields

        for field, value in self._json.items():
            if value is None:
                continue

            str_value = str(value).strip()
            field_lower = field.lower()

            # ── 1. Length check — long values suggest hallucination ──────────
            if len(str_value) > 500:
                warnings.append(
                    f"[SCHEMA] '{field}': value suspiciously long "
                    f"({len(str_value)} chars) — possible hallucination"
                )

            # ── 2. Repeated value check — same value in 3+ fields = hallucination ──
            if str_value not in values_seen:
                values_seen[str_value] = []
            values_seen[str_value].append(field)

            # ── 3. Field-type pattern validation ─────────────────────────────
            detected_type = None
            for ftype, hints in FIELD_TYPE_HINTS.items():
                if any(hint in field_lower for hint in hints):
                    detected_type = ftype
                    break

            if detected_type and detected_type in FIELD_PATTERNS:
                pattern = FIELD_PATTERNS[detected_type]
                if not pattern.search(str_value):
                    warnings.append(
                        f"[SCHEMA] '{field}': expected {detected_type} format, "
                        f"got '{str_value}' — may be incorrectly extracted"
                    )

            # ── 4. Email-specific check ───────────────────────────────────────
            if "email" in field_lower and value is not None:
                if "@" not in str_value:
                    warnings.append(
                        f"[SCHEMA] '{field}': value '{str_value}' does not "
                        f"look like a valid email address"
                    )

        # ── 5. Global repeated-value check ───────────────────────────────────
        for val, fields in values_seen.items():
            if len(fields) >= 3:
                warnings.append(
                    f"[SCHEMA] Possible hallucination — value '{val}' "
                    f"appears in {len(fields)} fields: {fields}"
                )

        self._validation_warnings = warnings

        if warnings:
            print("\t[SCHEMA VALIDATION] Issues found:")
            for w in warnings:
                print(f"\t  {w}")
        else:
            print("\t[SCHEMA VALIDATION] All fields passed validation ✓")

        return warnings

    def get_validation_warnings(self) -> list:
        """Return validation warnings from last validate_extracted_fields() call."""
        return self._validation_warnings

    def build_batch_prompt(self) -> str:
        """
        Build a single prompt that extracts ALL fields at once.
        Sends human-readable labels as context so Mistral understands
        what each internal field name means.
        Fixes Issue #196 — reduces N Ollama calls to 1.
        """
        if isinstance(self._target_fields, dict):
            fields_lines = "\n".join(
                f'  "{k}": null  // {v if v and v != k else k}'
                for k, v in self._target_fields.items()
            )
        else:
            fields_lines = "\n".join(
                f'  "{f}": null'
                for f in self._target_fields
            )

        prompt = f"""You are filling out an official form. Extract values from the transcript below.

FORM FIELDS (each line: "internal_key": null  // visible label on form):
{{
{fields_lines}
}}

RULES:
1. Return ONLY a valid JSON object — no explanation, no markdown, no extra text
2. Use the visible label (after //) to understand what each field means
3. Fill each key with the matching value from the transcript
4. If a value is not found in the transcript, use null
5. Never invent or guess values not present in the transcript
6. For multiple values (e.g. multiple victims), use a semicolon-separated string: "Name1; Name2"
7. Distinguish roles carefully: Officer/Employee is NOT the same as Victim or Suspect

TRANSCRIPT:
{self._transcript_text}

JSON:"""

        return prompt

    def build_prompt(self, current_field: str) -> str:
        """
        Legacy single-field prompt — kept for backward compatibility.
        Used as fallback if batch parsing fails.
        """
        field_lower = current_field.lower()
        is_plural = current_field.endswith('s') and not current_field.lower().endswith('ss')

        if any(w in field_lower for w in ['officer', 'employee', 'dispatcher', 'caller', 'reporting', 'supervisor']):
            role_guidance = """
ROLE: Extract the PRIMARY OFFICER/EMPLOYEE/DISPATCHER
- This is typically the person speaking or reporting the incident
- DO NOT extract victims, witnesses, or members of the public
- Example: "Officer Smith reporting... victims are John and Jane" → extract "Smith"
"""
        elif any(w in field_lower for w in ['victim', 'injured', 'affected', 'casualty', 'patient']):
            role_guidance = f"""
ROLE: Extract VICTIM/AFFECTED PERSON(S)
- Focus on people who experienced harm
- Ignore officers, dispatchers, and witnesses
{'- Return ALL names separated by ";"' if is_plural else '- Return the FIRST/PRIMARY victim'}
"""
        elif any(w in field_lower for w in ['location', 'address', 'street', 'place', 'where']):
            role_guidance = """
ROLE: Extract LOCATION/ADDRESS
- Extract WHERE the incident occurred
- Return only the incident location, not other addresses mentioned
"""
        elif any(w in field_lower for w in ['date', 'time', 'when', 'occurred', 'reported']):
            role_guidance = """
ROLE: Extract DATE/TIME
- Extract WHEN the incident occurred
- Return in the format it appears in the text
"""
        elif any(w in field_lower for w in ['phone', 'number', 'contact', 'tel']):
            role_guidance = "ROLE: Extract PHONE NUMBER — return exactly as it appears in text"
        elif any(w in field_lower for w in ['email', 'mail']):
            role_guidance = "ROLE: Extract EMAIL ADDRESS"
        elif any(w in field_lower for w in ['department', 'unit', 'division']):
            role_guidance = "ROLE: Extract DEPARTMENT/UNIT name"
        elif any(w in field_lower for w in ['title', 'job', 'role', 'rank', 'position']):
            role_guidance = "ROLE: Extract JOB TITLE or RANK"
        elif any(w in field_lower for w in ['id', 'badge', 'identifier']):
            role_guidance = "ROLE: Extract ID or BADGE NUMBER"
        elif any(w in field_lower for w in ['description', 'incident', 'detail', 'nature', 'summary']):
            role_guidance = "ROLE: Extract a brief INCIDENT DESCRIPTION"
        else:
            role_guidance = f"""
ROLE: Generic extraction for field "{current_field}"
{'- Return MULTIPLE values separated by ";" if applicable' if is_plural else '- Return the PRIMARY matching value'}
"""

        prompt = f"""
SYSTEM: You are extracting specific information from an incident report transcript.

FIELD TO EXTRACT: {current_field}
{'[SINGULAR - Extract ONE value]' if not is_plural else '[PLURAL - Extract MULTIPLE values separated by semicolon]'}

EXTRACTION RULES:
{role_guidance}

CRITICAL RULES:
1. Read the ENTIRE text before answering
2. Extract ONLY what belongs to this specific field
3. Return values exactly as they appear in the text
4. If not found, return: -1

TRANSCRIPT:
{self._transcript_text}

ANSWER: Return ONLY the extracted value(s), nothing else."""

        return prompt

    def main_loop(self):
        """
        Single batch Ollama call — extracts ALL fields in one request.
        Falls back to per-field extraction if JSON parsing fails.
        Runs schema validation after extraction.
        Fixes Issue #196 (O(N) → O(1) LLM calls).
        """
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        # Get field keys for result mapping
        if isinstance(self._target_fields, dict):
            field_keys = list(self._target_fields.keys())
        else:
            field_keys = list(self._target_fields)

        # ── Single batch call ─────────────────────────────────────
        prompt = self.build_batch_prompt()
        payload = {"model": "mistral", "prompt": prompt, "stream": False}

        try:
            response = requests.post(ollama_url, json=payload)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Could not connect to Ollama at {ollama_url}. "
                "Please ensure Ollama is running and accessible."
            )
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Ollama returned an error: {e}")

        raw = response.json()["response"].strip()

        # Strip markdown code fences if Mistral wraps in ```json ... ```
        raw = raw.replace("```json", "").replace("```", "").strip()

        print("----------------------------------")
        print("\t[LOG] Raw Mistral batch response:")
        print(raw)

        # ── Parse JSON response ───────────────────────────────────
        try:
            extracted = json.loads(raw)
            for key in field_keys:
                val = extracted.get(key)
                if val and str(val).lower() not in ("null", "none", ""):
                    self._json[key] = val
                else:
                    self._json[key] = None

            print("\t[LOG] Batch extraction successful.")

        except json.JSONDecodeError:
            print("\t[WARN] Batch JSON parse failed — falling back to per-field extraction")
            self._json = {}
            self._fallback_per_field(ollama_url, field_keys)

        # ── Schema validation ─────────────────────────────────────
        self.validate_extracted_fields()

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def _fallback_per_field(self, ollama_url: str, field_keys: list):
        """
        Legacy per-field extraction — used only when batch JSON parse fails.
        """
        print("\t[LOG] Running fallback per-field extraction...")

        for field in field_keys:
            if isinstance(self._target_fields, dict):
                label = self._target_fields.get(field, field)
                if not label or label == field:
                    label = field
            else:
                label = field

            prompt = self.build_prompt(label)
            payload = {"model": "mistral", "prompt": prompt, "stream": False}

            try:
                response = requests.post(ollama_url, json=payload)
                response.raise_for_status()
                parsed_response = response.json()["response"]
                self.add_response_to_json(field, parsed_response)
            except Exception as e:
                print(f"\t[WARN] Failed to extract field '{field}': {e}")
                self._json[field] = None

    def add_response_to_json(self, field, value):
        """
        Add extracted value under field name.
        Handles plural (semicolon-separated) values.
        """
        value = value.strip().replace('"', "")
        parsed_value = None

        if value != "-1":
            parsed_value = value

        if parsed_value and ";" in parsed_value:
            parsed_value = self.handle_plural_values(parsed_value)

        if field in self._json:
            existing = self._json[field]
            if isinstance(existing, list):
                if isinstance(parsed_value, list):
                    existing.extend(parsed_value)
                else:
                    existing.append(parsed_value)
            else:
                self._json[field] = [existing, parsed_value]
        else:
            self._json[field] = parsed_value

    def handle_plural_values(self, plural_value):
        """
        Split semicolon-separated values into a list.
        "Mark Smith; Jane Doe" → ["Mark Smith", "Jane Doe"]
        """
        if ";" not in plural_value:
            raise ValueError(
                f"Value is not plural, doesn't have ; separator, Value: {plural_value}"
            )

        print(f"\t[LOG]: Formatting plural values for JSON, [For input {plural_value}]...")
        values = [v.strip() for v in plural_value.split(";") if v.strip()]
        print(f"\t[LOG]: Resulting formatted list of values: {values}")
        return values

    def get_data(self):
        return self._json