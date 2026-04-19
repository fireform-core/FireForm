import json
import os
import requests


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None):
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields      # dict or list
        self._json = json                        # dictionary of extracted fields
        self._timeline = None                    # stores extracted timeline

    def type_check_all(self):
        """Validate input types."""
        
        if type(self._transcript_text) is not str:
            raise TypeError("Transcript must be text.")

        if not isinstance(self._target_fields, (dict, list)):
            raise TypeError("Target fields must be dict or list.")
    
    def build_prompt(self, current_field):
        """
        Builds a prompt for a single field (used by original main_loop).
        """
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fill out JSON files with information extracted from transcribed voice recordings. 
            You will receive the transcription, and the name of the JSON field whose value you have to identify in the context. Return 
            only a single string containing the identified value for the JSON field. 
            If the field name is plural, and you identify more than one possible value in the text, return both separated by a ";".
            If you don't identify the value in the provided text, return "-1".
            ---
            DATA:
            Target JSON field to find in text: {current_field}
            
            TEXT: {self._transcript_text}
            """
        return prompt

# new def for the timeline 
    def _build_timeline_prompt(self):
        """
        NEW: Build a single prompt that asks for both the standard fields and a timeline array.
        """
        # Format the list of target fields nicely
        field_list = "\n".join([f"  - {field}" for field in self._target_fields])

#2 part is the new feature  ,a timeline for the incidents that occured

        prompt = f"""
You are an AI assistant designed to help fill out incident reports.  
You will receive a transcribed voice recording.  
Extract the information and return a **valid JSON object** with two keys:

1. "fields": an object containing the following fields (if a field is not present, set its value to "-1"):
{field_list}

2. "timeline": an array of events. Each event should be an object with:
   - "timestamp": string (e.g., "14:30") – if no timestamp, use the approximate order
   - "event_type": one of ["arrival", "containment", "transport", "departure", "other"] (infer from context)
   - "description": a brief summary of the event
   - "location": optional string
   - "personnel": optional string (names or roles)

If a timeline cannot be constructed, return an empty array.

Return ONLY the JSON object, with no extra text.

TEXT:
{self._transcript_text}
"""
        return prompt

    def main_loop(self):
        """
        Original method – processes fields one by one (sequential calls).
        """
        self.type_check_all()
        for field in self._target_fields:
            prompt = self.build_prompt(field)
            # print

            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_url = f"{ollama_host}/api/generate"

            payload = {
                "model": os.getenv("OLLAMA_MODEL", "mistral"),
                "prompt": prompt,
                "stream": False,
            }

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

            json_data = response.json()
            parsed_response = json_data["response"]
            self.add_response_to_json(field, parsed_response)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def main_loop_with_timeline(self):
        """
        NEW: Single LLM call that returns both fields and timeline.
        """
        self.type_check_all()

        prompt = self._build_timeline_prompt()

        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        payload = {
            "model": os.getenv("OLLAMA_MODEL", "mistral"),
            "prompt": prompt,
            "stream": False,
        }

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

        json_data = response.json()
        llm_output = json_data["response"]

        try:
            parsed = json.loads(llm_output)
            self._json = parsed.get("fields", {})
            self._timeline = parsed.get("timeline", [])
        except json.JSONDecodeError:

            # Fallback: treating the whole output as fields (backward Compatibility)

            self._json = {field: llm_output for field in self._target_fields}
            self._timeline = []

        print("----------------------------------")
        print("\t[LOG] Resulting JSON from the input text:")
        print(json.dumps(self._json, indent=2))
        if self._timeline:
            print("\t[LOG] Extracted timeline:")
            print(json.dumps(self._timeline, indent=2))
        print("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field, value):
        """
        Adds the extracted value to the JSON dictionary.
        """
        value = value.strip().replace('"', "")

        if value == "-1":
                parsed_value = None
        elif ";" in value:
                parsed_value = self.handle_plural_values(value)
        else:
                parsed_value = value

        self._json[field] = parsed_value

        return

    def handle_plural_values(self, plural_value):
        """
        Splits a string like 'value1; value2' into a list.
        """
        if ";" not in plural_value:
            raise ValueError(
                f"Value is not plural, doesn't have ; separator, Value: {plural_value}"
            )

        print(f"\t[LOG]: Formatting plural values for JSON, [For input {plural_value}]...")
        values = [v.strip() for v in plural_value.split(";")]

        #  whitespaceClean up
        for i in range(len(values)):
            current = i + 1
            if current < len(values):
                clean_value = values[current].lstrip()
                values[current] = clean_value

        print(f"\t[LOG]: Resulting formatted list of values: {values}")

        return values

    def get_data(self):
        """
        Returns the extracted field dictionary (backward compatible).
        """
        return self._json

    def get_timeline(self):
        """
        Returns the extracted timeline (if any).
        """
        return self._timelinemaking
