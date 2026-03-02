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
            prompt = self.build_prompt(field)
            # print(prompt)
            # ollama_url = "http://localhost:11434/api/generate"
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_url = f"{ollama_host}/api/generate"

            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False,  # don't really know why --> look into this later.
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
            parsed_response = json_data["response"]
            # print(parsed_response)
            self.add_response_to_json(field, parsed_response)

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

    def build_batch_prompt(self):
        """
        Builds a single prompt that asks the LLM to extract ALL target fields
        at once and return them as a JSON object.
        This replaces N sequential API calls with a single round-trip.
        """
        fields_list = json.dumps(list(self._target_fields.keys()), indent=2)
        prompt = f"""
SYSTEM PROMPT:
You are an AI assistant that extracts structured data from incident transcriptions.
Extract values for ALL of the following JSON fields from the text below.
Return ONLY a valid JSON object with no extra explanation, commentary, or markdown fences.
If a field is plural and multiple values exist in the text, use a list of strings.
If a value cannot be found in the text, use null.

FIELDS TO EXTRACT:
{fields_list}

TEXT:
{self._transcript_text}

OUTPUT FORMAT:
{{
  "field_name": "extracted value or null",
  ...
}}
"""
        return prompt

    def main_loop_batch(self):
        """
        Single-call extraction — replaces the N sequential calls in main_loop().
        Sends one prompt containing all target fields and parses the JSON response.
        Falls back to main_loop() if the LLM does not return valid JSON.
        """
        prompt = self.build_batch_prompt()
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        payload = {
            "model": "mistral",
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

        raw = response.json()["response"].strip()

        # Strip markdown code fences if the model wrapped the output
        if raw.startswith("```"):
            parts = raw.split("```")
            # parts[1] is the fenced block; drop a leading "json" language tag if present
            raw = parts[1].lstrip("json").strip()

        try:
            extracted = json.loads(raw)
        except json.JSONDecodeError as e:
            print(
                f"\t[WARN] main_loop_batch: LLM did not return valid JSON ({e}). "
                "Falling back to sequential main_loop()."
            )
            return self.main_loop()

        # Populate self._json using the existing add_response_to_json logic
        for field in self._target_fields.keys():
            value = extracted.get(field)
            if value is None:
                self.add_response_to_json(field, "-1")
            elif isinstance(value, list):
                self.add_response_to_json(field, "; ".join(str(v) for v in value))
            else:
                self.add_response_to_json(field, str(value))

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text (batch mode):")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def get_data(self):
        return self._json
