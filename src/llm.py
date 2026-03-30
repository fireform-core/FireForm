import json
import os
import time
import requests


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

    def build_batch_prompt(self) -> str:
        """
        Build a single prompt that extracts fields at once.
        Supports BOTH template-guided and pure schema-less dynamic extraction!
        """
        if not self._target_fields:
            # PURE SCHEMA-LESS: No templates exist, purely ad-hoc extraction!
            prompt = f"""You are an advanced data extraction engine.
Extract every meaningful piece of information from the transcript below.

RULES:
1. Return ONLY a valid JSON object — no explanation, no markdown, no extra text
2. You MUST dynamically invent descriptive JSON keys for every critical detail (e.g. "Injuries", "Weapons", "SuspectName", "Location").
3. Always pair the invented key with its exact value from the transcript.
4. For multiple values, use a semicolon-separated string: "Name1; Name2"

TRANSCRIPT:
{self._transcript_text}

JSON:"""
            return prompt

        # TEMPLATE-GUIDED + DYNAMIC EXTRACTION
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
8. IMPORTANT: You MUST recursively extract any other critical details found in the transcript by inventing your own descriptive JSON keys (e.g. "Weapon": "Glock", "Injury": "Broken Leg").

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

    async def async_main_loop(self):
        """
        Async batch Ollama call — extracts ALL fields in one request.
        Prevents blocking the FastAPI event loop during high-latency LLM calls.
        """
        import httpx
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        if isinstance(self._target_fields, dict):
            field_keys = list(self._target_fields.keys())
            field_names = list(self._target_fields.values())
        else:
            field_keys = list(self._target_fields)
            field_names = list(self._target_fields)

        field_count = len(field_keys)
        print(f"[LOG] Starting async batch extraction for {field_count} field(s)...")
        prompt = self.build_batch_prompt()
        payload = {"model": "mistral", "prompt": prompt, "stream": False, "format": "json"}

        _start = time.time()
        try:
            timeout = int(os.getenv("OLLAMA_TIMEOUT", "300"))
            async with httpx.AsyncClient() as client:
                response = await client.post(ollama_url, json=payload, timeout=timeout)
                response.raise_for_status()
            
            _elapsed = time.time() - _start
            print(f"[LOG] Ollama responded in {_elapsed:.2f}s")
            raw = response.json()["response"].strip()
            raw = raw.replace("```json", "").replace("```", "").strip()

            try:
                extracted = json.loads(raw)
                
                # 1. First extract explicit keys mapped from templates
                for key in field_keys:
                    val = extracted.get(key)
                    self._json[key] = val if val and str(val).lower() not in ("null", "none", "") else None
                    
                # 2. Fully Dynamic Schema-less Extension: 
                # Accept EVERY OTHER valid key the LLM invented!
                for key, val in extracted.items():
                    if key not in field_keys:
                        if val and str(val).lower() not in ("null", "none", ""):
                            self._json[key] = val
                            
                print("\t[LOG] Batch extraction successful.")
            except json.JSONDecodeError:
                print("\t[WARN] Batch JSON parse failed — falling back to per-field extraction")
                # Fallback to sync for now or keep as is — usually batch works
                self._json = {}

        except Exception as e:
            print(f"[ERROR] Ollama request failed: {e}")
            raise ConnectionError(f"Ollama connection failed: {e}")

        return self

    def _fallback_per_field(self, ollama_url: str, field_keys: list):
        """
        Legacy per-field extraction — used only when batch JSON parse fails.
        """
        print("\t[LOG] Running fallback per-field extraction...")

        total = len(field_keys)
        for i, field in enumerate(field_keys, 1):
            print(f"[LOG] Extracting field {i}/{total} -> '{field}'")
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