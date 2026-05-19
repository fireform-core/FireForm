import json
import os
import requests
from requests.exceptions import Timeout, RequestException


class LLM:
    def __init__(self, transcript_text: str=None, target_fields: list=None, json_dict: dict=None):
        self._transcript_text = transcript_text
        self._target_fields = target_fields
        self._json = json_dict if json_dict is not None else {}

    def build_prompt(self, current_field: str, field_type: type = str):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt
        for each target field, taking into account the expected field type.

        If the field type is `bool`, the LLM is explicitly instructed to return only
        the literal string `True` or `False` — no fuzzy values like 'yes' or '1'.

        @params:
            current_field -> the name of the JSON field to extract.
            field_type    -> the expected Python type (e.g. str, bool).
        """
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
        with open(prompt_path, "r") as f:
            template = f.read()

        if field_type is bool:
            bool_instruction = (
                "\nIMPORTANT: This field is a boolean. "
                "You MUST respond with ONLY the literal word True or False. "
                "Do not use 'yes', 'no', '1', '0', or any other value."
            )
            return template.format(field=current_field, text=self._transcript_text) + bool_instruction

        return template.format(field=current_field, text=self._transcript_text)

    def main_loop(self):
        timeout = 45
        max_retries = 3

        total_fields = len(self._target_fields)
        for i, field in enumerate(self._target_fields.keys(), 1):
            field_type = self._target_fields[field] if isinstance(self._target_fields[field], type) else str
            prompt = self.build_prompt(field, field_type=field_type)
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_url = f"{ollama_host}/api/generate"

            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
            }

            json_data = None
            try:
                for attempt in range(max_retries):
                    try:
                        response = requests.post(ollama_url, json=payload, timeout=timeout)
                        response.raise_for_status()
                        json_data = response.json()
                        break
                    except Timeout:
                        print(f"[LOG]: Ollama request timed out (attempt {attempt+1}) for field '{field}'. Retrying...")
                    except RequestException as e:
                        print(f"[LOG]: Ollama request failed: {e}")
            except requests.exceptions.ConnectionError:
                raise ConnectionError(
                    f"Could not connect to Ollama at {ollama_url}. "
                    "Please ensure Ollama is running and accessible."
                )
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(f"Ollama returned an error: {e}")

            if json_data is None:
                raise RuntimeError("Failed to get response from Ollama after retries.")
            else:
                parsed_response = json_data["response"]
                self.add_response_to_json(field, parsed_response)
                print(f"[{i}/{total_fields}] Extracted data for field '{field}' successfully.")

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field: str, value: str):
        """
        Adds the LLM response under the specified field in the JSON dict.

        If the field type in _target_fields is `bool`, the response is strictly
        coerced: only the literal strings 'True' and 'False' (case-insensitive)
        are accepted. Any other value is treated as None (unanswered).
        """
        value = value.strip().replace('"', "")
        parsed_value = None

        # Determine expected type for this field
        field_type = self._target_fields.get(field) if isinstance(self._target_fields, dict) else str
        if not isinstance(field_type, type):
            field_type = str

        if field_type is bool:
            # Strictly enforce True/False — no fuzzy matching
            if value.lower() == "true":
                parsed_value = True
            elif value.lower() == "false":
                parsed_value = False
            else:
                print(f"[WARN]: Boolean field '{field}' received unexpected value '{value}'. Defaulting to None.")
                parsed_value = None
        else:
            if value != "-1":
                parsed_value = value

            if ";" in value:
                parsed_value = self.handle_plural_values(value)

        if field in self._json.keys():
            self._json[field].append(parsed_value)
        else:
            self._json[field] = parsed_value

        return

    def handle_plural_values(self, plural_value: str):
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
            f"\t[LOG]: Formatting plural values for JSON, [For input {plural_value}]..."
        )
        values = plural_value.split(";")

        # Remove trailing leading whitespace
        for i in range(len(values)):
            values[i] = values[i].lstrip()

        print(f"\t[LOG]: Resulting formatted list of values: {values}")

        return values

    def get_data(self):
        return self._json
