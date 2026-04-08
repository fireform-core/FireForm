import json
import os
import requests
from pydantic import create_model, Field


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None):
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List, contains the template field.
        self._json = json  # dictionary

    def type_check_all(self):
        if type(self._transcript_text) is not str:
            raise TypeError(
                f"ERROR in LLM() attributes ->\
                Transcript must be text. Input:\n\ttranscript_text: {self._transcript_text}"
            )
        # Updated to handle both list and dict based on earlier usage
        if not isinstance(self._target_fields, (list, dict)):
            raise TypeError(
                f"ERROR in LLM() attributes ->\
                Target fields must be a list or dict. Input:\n\ttarget_fields: {self._target_fields}"
            )

    def _get_fields_iterable(self):
        """Helper to safely iterate over fields whether they are passed as a list or a dict."""
        if isinstance(self._target_fields, dict):
            return list(self._target_fields.keys())
        return self._target_fields

    def build_schema(self):
        """Dynamically generates a Pydantic schema based on target fields."""
        field_definitions = {}
        for field in self._get_fields_iterable():
            clean_name = field.replace(" ", "_").replace("'", "").replace("-", "_").replace("/", "_")
            if clean_name and clean_name[0].isdigit():
                clean_name = "f_" + clean_name
                
            description = f"Extract the value for '{field}'. If not found, return an empty string. If multiple values, separate by ';'."
            field_definitions[clean_name] = (str, Field(default="", description=description))
        
        DynamicModel = create_model('FormExtraction', **field_definitions)
        return DynamicModel.model_json_schema()

    def map_schema_to_json(self, extracted_data):
        """Maps the strictly typed LLM output back to the original PDF field names."""
        for original_field in self._get_fields_iterable():
            clean_name = original_field.replace(" ", "_").replace("'", "").replace("-", "_").replace("/", "_")
            if clean_name and clean_name[0].isdigit():
                clean_name = "f_" + clean_name
                
            if clean_name in extracted_data:
                raw_value = extracted_data[clean_name]
                
                if not raw_value or raw_value == "-1":
                    continue
                    
                if ";" in raw_value:
                    values = [v.strip() for v in raw_value.split(";") if v.strip()]
                    self._json[original_field] = values
                else:
                    self._json[original_field] = raw_value

    def main_loop(self):
        self.type_check_all()
        
        fields_list = self._get_fields_iterable()
        print(f"\t[LOG] Extracting {len(fields_list)} fields using Pydantic structured output...")
        
        schema = self.build_schema()
        
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fillout json files with information extracted from transcribed voice recordings. 
            You will receive the transcription and must extract the values for all fields defined in the JSON schema.
            Return ONLY a valid JSON object matching the provided schema. No markdown, no extra text.
            If you don't identify the value in the provided text, leave it as an empty string.
            ---
            TEXT: {self._transcript_text}
            """

        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        payload = {
            "model": "mistral",
            "prompt": prompt,
            "format": schema,
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

        # parse response
        json_data = response.json()
        try:
            parsed_response = json.loads(json_data["response"])
        except json.JSONDecodeError:
            print("\t[ERROR] LLM did not return valid JSON. Defaulting to empty extraction.")
            parsed_response = {}
            
        self.map_schema_to_json(parsed_response)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def get_data(self):
        return self._json