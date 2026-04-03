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
        text_model = os.getenv("FIREFORM_TEXT_MODEL", "gemma3:4b")
        print(f"[LOG] Starting async batch extraction for {field_count} field(s) using {text_model}...")
        prompt = self.build_batch_prompt()
        payload = {"model": text_model, "prompt": prompt, "stream": False, "format": "json"}

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
            text_model = os.getenv("FIREFORM_TEXT_MODEL", "gemma3:4b")
            payload = {"model": text_model, "prompt": prompt, "stream": False}

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

    # ── Vision Model Methods ────────────────────────────────────────

    import base64
    
    async def async_vision_scan_fields(self, image_bytes: bytes) -> list[dict]:
        """
        Passes a page image to the Vision model to map out form fields.
        Returns a list of dicts: {"label": "...", "x": ..., "y": ..., "w": ..., "h": ...}
        where x, y, w, h are percentages (0-100) of the page width/height.
        """
        import base64
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"
        
        vision_model = os.getenv("FIREFORM_VISION_MODEL", "gemma3:4b")
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        # FIX #3: Do NOT use format:json — it forces a dict root which breaks list output.
        # Instead, write a very explicit, direct prompt that tells Gemma EXACTLY what to output.
        prompt = '''Look at this document image carefully. Find every blank line, input field, or checkbox that a person is expected to fill in.

For each field you find, output exactly one JSON object on its own line in this format:
{"label": "snake_case_field_name", "x": 10.5, "y": 25.3, "w": 40.0, "h": 3.5, "type": "text"}

Rules:
- label: a descriptive snake_case name for the field (e.g. full_name, email_address, phone_number, street_address, comments)
- x: left edge position as a percentage of the image width (0 to 100)
- y: top edge position as a percentage of the image height (0 to 100)
- w: width of the blank as a percentage of the image width (0 to 100)
- h: height of the blank as a percentage of the image height (0 to 100)
- type: "text" for a text line, "checkbox" for a tick box

Output ONLY the JSON objects, one per line. No explanation. No markdown. No extra text.'''
        
        payload = {
            "model": vision_model,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
            # NOTE: No "format": "json" — that forces a dict root which kills list output!
        }

        try:
            # timeout=900s (15 min) — vision is slow but only runs ONCE per template!
            response = requests.post(ollama_url, json=payload, timeout=900)
            response.raise_for_status()
            res_text = response.json().get("response", "").strip()
            
            print(f"\n\n🚨 [VISION RAW RESPONSE] 🚨\n{res_text}\n\n")
            
            # Strip markdown fences if present
            if res_text.startswith("```json"):
                res_text = res_text[7:]
            if res_text.startswith("```"):
                res_text = res_text[3:]
            if res_text.endswith("```"):
                res_text = res_text[:-3]
            res_text = res_text.strip()

            # FIX #1: Robust multi-format parser.
            # Gemma might return a bare list, a wrapped dict, or newline-delimited objects.
            fields = []
            
            # Strategy A: Try parsing whole thing as JSON
            try:
                data = json.loads(res_text)
                if isinstance(data, list):
                    fields = data  # Perfect bare list []
                elif isinstance(data, dict):
                    # Gemma wrapped it: {"fields": [...]} or {"items": [...]}
                    for v in data.values():
                        if isinstance(v, list):
                            fields = v
                            break
            except json.JSONDecodeError:
                # Strategy B: Parse line-by-line (one JSON object per line)
                print("[VISION] Falling back to line-by-line JSON parsing...")
                for line in res_text.splitlines():
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            obj = json.loads(line)
                            if "label" in obj:
                                fields.append(obj)
                        except json.JSONDecodeError:
                            pass

            # Validate fields have minimum required keys
            valid_fields = [
                f for f in fields
                if isinstance(f, dict) and "label" in f and "x" in f and "y" in f
            ]
            print(f"[VISION] Successfully parsed {len(valid_fields)} valid fields.")
            return valid_fields
            
        except Exception as e:
            print(f"[ERROR] Vision Scan Failed: {e}")
            return []

    async def async_vision_describe_scene(self, image_bytes: bytes) -> str:
        """
        Takes a scene photo and generates a professional incident narrative to feed into the Data Lake.
        """
        import base64
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"
        vision_model = os.getenv("FIREFORM_VISION_MODEL", "gemma3:4b")
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        prompt = '''
You are a professional first responder describing an incident scene. 
Look at the provided image and generate a concise but highly detailed incident narrative.
Describe any structures, vehicles, hazards, visible injuries, number of units involved, and overall context.
Use professional, objective reporting language.
        '''
        
        payload = {
            "model": vision_model,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
        }

        try:
            response = requests.post(ollama_url, json=payload, timeout=900)
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            print(f"[ERROR] Scene Description Failed: {e}")
            return "Failed to process image scene."
    @staticmethod
    async def async_semantic_map(master_json: dict, target_pdf_fields: list) -> dict:
        """
        AI Semantic Mapper: Maps unstructured Data Lake JSON to specific PDF form fields.
        """
        import httpx
        import json
        import os
        
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"
        
        # Prepare the target fields list for the prompt
        fields_str = "\n".join([f'- "{f}"' for f in target_pdf_fields])
        
        prompt = f"""You are an intelligent data mapping system.
I will give you a JSON object containing extracted incident details, and a list of target form fields.
Your job is to map the available details into the target form fields based on human semantics.

TARGET FORM FIELDS REQUIRED:
{fields_str}

AVAILABLE INCIDENT DATA:
{json.dumps(master_json, indent=2)}

RULES:
1. Return ONLY a valid JSON object. No markdown, no explanations, no text before or after the JSON braces "{{}}".
2. The JSON keys MUST EXACTLY match the TARGET FORM FIELDS requested above.
3. If the available data does not contain information suitable for a target field, output null for that field.
4. Do not invent information not present in the available incident data! Look for synonyms (e.g., if target is "FullName", look for "Speaker", "ApplicantName", "Officer", etc. in the available data).

MAPPED JSON OUTPUT:"""

        text_model = os.getenv("FIREFORM_TEXT_MODEL", "gemma3:4b")
        payload = {"model": text_model, "prompt": prompt, "stream": False, "format": "json"}
        print(f"[SEMANTIC MAPPER] Mapping {len(master_json)} lake fields to {len(target_pdf_fields)} PDF fields using {text_model}...")
        
        try:
            timeout = int(os.getenv("OLLAMA_TIMEOUT", "300"))
            async with httpx.AsyncClient() as client:
                response = await client.post(ollama_url, json=payload, timeout=timeout)
                response.raise_for_status()
                
            raw = response.json()["response"].strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            
            mapped_data = json.loads(raw)
            mapped_count = sum(1 for v in mapped_data.values() if v is not None and str(v).lower() not in ("null", "none", ""))
            print(f"[SEMANTIC MAPPER] Successfully mapped {mapped_count} out of {len(target_pdf_fields)} required PDF fields.")
            return mapped_data
            
        except Exception as e:
            print(f"[ERROR] Semantic mapping failed: {e}")
            # Fallback to empty if it entirely fails, so standard processing can try fallback exact matches
            return {}