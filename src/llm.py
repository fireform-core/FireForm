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

    def build_prompt(self, current_field):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt for each target field.
        @params: current_field -> represents the current element of the json that is being prompted.
        """
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to extract information from transcribed voice recordings. 
            You must return your answer STRICTLY as a valid JSON object with two keys: "value" and "quote".
            - "value": The identified value for the field. If not found, use "-1". If plural, separate with ";".
            - "quote": The exact sentence or phrase from the text that justifies your value. If not found, use "N/A".
            ---
            DATA:
            Target JSON field to find in text: {current_field}
            
            TEXT: {self._transcript_text}
            """

        return prompt

    def main_loop(self):
        # self.type_check_all()
        for field in self._target_fields:
            prompt = self.build_prompt(field)
            # print(prompt)
            # ollama_url = "http://localhost:11434/api/generate"
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_url = f"{ollama_host}/api/generate"

            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False, # don't really know why --> look into this later.
                "format": "json"
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
                parsed_obj = json.loads(json_data["response"])
                val = parsed_obj.get("value", "-1")
                quote = parsed_obj.get("quote", "N/A")
            except json.JSONDecodeError:
                val = "-1"
                quote = "JSON Parse Error"

            self.add_response_to_json(field, val, quote)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field, value, quote="N/A"):
        """
        this method adds the following value under the specified field,
        or under a new field if the field doesn't exist, to the json dict
        """
        # SAFETY CHECK: If the LLM returns a list, join it with semicolons
        if isinstance(value, list):
            value = ";".join([str(v) for v in value])
        # If it returns a number or boolean, cast it to a string
        elif not isinstance(value, str):
            value = str(value)

        # Now it's guaranteed to be a string
        value = value.strip().replace('"', "")
        parsed_value = None

        if value != "-1":
            parsed_value = value

        if ";" in value:
            parsed_value = self.handle_plural_values(value)
            
        entry = {"value": parsed_value, "quote": quote}

        if field in self._json.keys():
            # If it's already a list, append. Otherwise convert to list.
            if isinstance(self._json[field], list):
                self._json[field].append(entry)
            else:
                self._json[field] = [self._json[field], entry]
        else:
            self._json[field] = entry

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
