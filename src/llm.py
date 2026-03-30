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

    def build_batch_prompt(self, field_list):
        """
        Creates a prompt for batch extraction of all fields in JSON format.
        """
        prompt = f"""
            SYSTEM PROMPT:
            You are an AI assistant designed to extract information from transcribed voice recordings and format it as JSON.
            You will receive the transcription and a list of JSON fields to identify.
            Your output MUST be a valid JSON object where the keys are the field names and the values are the identified data.
            If a value is not identified, use "-1".
            If a field name is plural and you identify more than one value, use a ";" separated string.

            Example format:
            {{
                "Field1": "value",
                "Field2": "value1; value2",
                "Field3": "-1"
            }}

            ---
            DATA:
            Target JSON fields: {list(field_list)}

            TEXT: {self._transcript_text}
            """
        return prompt

    def main_loop(self):
        # self.type_check_all()
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"
        model_name = os.getenv("OLLAMA_MODEL", "mistral")

        prompt = self.build_batch_prompt(self._target_fields.keys())

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }

        print(f"\t[LOG] Sending batch request to Ollama ({model_name})...")
        try:
            response = requests.post(ollama_url, json=payload, timeout=300)
            response.raise_for_status()
            json_data = response.json()
            raw_response = json_data["response"]

            # Parse the extracted JSON
            try:
                extracted_data = json.loads(raw_response)
            except json.JSONDecodeError:
                # Fallback: find the first { and last }
                start = raw_response.find('{')
                end = raw_response.rfind('}')
                if start != -1 and end != -1:
                    extracted_data = json.loads(raw_response[start:end+1])
                else:
                    raise ValueError("Could not parse JSON from LLM response.")

            # Process each field
            for field, value in extracted_data.items():
                self.add_response_to_json(field, str(value))

        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Could not connect to Ollama at {ollama_url}. "
                "Please ensure Ollama is running and accessible."
            )
        except Exception as e:
            raise RuntimeError(f"Ollama/Extraction error: {e}")

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
