import json
import os
import requests
from api.services.prompt_builder import build_extraction_prompt
from src.validation import validate_extraction

def safe_extract_value(response: str):
    if not response:
        return None

    response = response.strip()

    
    response = response.replace('"', '').replace("'", "")

    
    if ":" in response:
        response = response.split(":")[-1].strip()

    
    response = response.split("\n")[0]

    
    if response.lower() in ["-1", "none", "null", "not found"]:
        return None


    if len(response) > 200:
        return None

    return response

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
        elif type(self._target_fields) is not list:
            raise TypeError(
                f"ERROR in LLM() attributes ->\
                Target fields must be a list. Input:\n\ttarget_fields: {self._target_fields}"
            )

    def build_prompt(self, current_field):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt for each target field.
        @params: current_field -> represents the current element of the json that is being prompted.
        """
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fillout json files with information extracted from transcribed voice recordings. 
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

    def main_loop(self):
        # self.type_check_all()
        for field in self._target_fields.keys():
            # print(prompt)
            # ollama_url = "http://localhost:11434/api/generate"
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_url = f"{ollama_host}/api/generate"

            base_prompt = build_extraction_prompt(self._transcript_text)

            prompt = f"""
            {base_prompt}

            Focus specifically on extracting the value for this field:
            {field}

            Return only the extracted value as a plain string. Do not return JSON.
            """

            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False,  # streaming disabled; using single response mode
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
            raw_response = json_data["response"]
            parsed_response = safe_extract_value(raw_response)
            # print(parsed_response)
            self.add_response_to_json(field, parsed_response)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field, value):
        value = value.strip().replace('"', "") if value else None
        parsed_value = None

        if value:
            parsed_value = value
        else:
            parsed_value = {
                "value": None,
                "requires_review": True
            }

        if value and ";" in value:
            parsed_value = self.handle_plural_values(value)

        if field in self._json.keys():
            self._json[field].append(parsed_value)
        else:
            self._json[field] = parsed_value

        return


    def handle_plural_values(self, plural_value):
        """
         This method handles plural values.
        """
        if ";" not in plural_value:
            raise ValueError(
                f"Value is not plural, doesn't have ; separator, Value: {plural_value}"
            )

        values = plural_value.split(";")

        for i in range(len(values)):
            values[i] = values[i].strip()

        return values

    def get_data(self):
        validated_data, errors = validate_extraction(self._json)

        if errors:
            print("[Validation Warning]", errors)

        return validated_data
