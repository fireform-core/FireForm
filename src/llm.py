import json
import os
import requests


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

    def build_prompt(self, fields_list):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt for all target fields combined.
        """
        import json
        fields_json = json.dumps(fields_list)
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fill out json files with information extracted from transcribed voice recordings. 
            You will receive the transcription and a list of JSON field names whose values you have to identify in the context. 
            Return ONLY a valid JSON object where the keys are the field names and the values are the extracted strings.
            If a field name implies multiple values, and you identify more than one possible value in the text, return both separated by a ";".
            If you don't identify the value in the provided text, return "-1".
            Do not include any formatting, markdown, or chat outside of the JSON object.
            ---
            DATA:
            Target JSON fields to find in text: {fields_json}
            
            TEXT: {self._transcript_text}
            """

        return prompt

    def main_loop(self):
        # We extract all field names into a list
        fields_list = list(self._target_fields.keys())
        prompt = self.build_prompt(fields_list)
        
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        payload = {
            "model": "llama3",
            "prompt": prompt,
            "stream": False,
            "format": "json",  # Force Ollama to return structured JSON
        }

        try:
            print(f"\t[LOG] Sending 1 batch request to Ollama for {len(fields_list)} fields...")
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
        parsed_response = json_data["response"]
        
        import json
        try:
            extracted_data = json.loads(parsed_response)
        except json.JSONDecodeError:
            print(f"\t[ERROR] Could not parse Ollama response as JSON: {parsed_response}")
            extracted_data = {}

        # Add each extracted value to our internal _json using the existing method
        for field in fields_list:
            value = str(extracted_data.get(field, "-1"))
            self.add_response_to_json(field, value)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field, value):
        """
        this method adds the following value under the specified field,
        or under a new field if the field doesn't exist, to the json dict
        """
        value = value.strip().replace('"', "")
        parsed_value = None

        if value != "-1":
            parsed_value = value

        if ";" in value:
            parsed_value = self.handle_plural_values(value)

        if field in self._json.keys():
            self._json[field].append(parsed_value)
        else:
            self._json[field] = parsed_value

        return

    def handle_plural_values(self, plural_value):
        """
        This method handles plural values.
        Takes in strings of the form 'value1; value2; value3; ...; valueN'
        returns a list with the respective values -> [value1, value2, value3, ..., valueN]
        """
        if ";" not in plural_value:
            raise ValueError(
                f"Value is not plural, doesn't have ; separator, Value: {plural_value}"
            )

        print(
            f"\t[LOG]: Formating plural values for JSON, [For input {plural_value}]..."
        )
        values = plural_value.split(";")

        # Remove trailing leading whitespace
        for i in range(len(values)):
            current = i + 1
            if current < len(values):
                clean_value = values[current].lstrip()
                values[current] = clean_value

        print(f"\t[LOG]: Resulting formatted list of values: {values}")

        return values

    def get_data(self):
        return self._json
