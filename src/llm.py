import json
import os
import time
from typing import Callable

import requests
from requests.exceptions import Timeout, RequestException


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

    def _post_to_ollama_with_retry(self, url, payload):
        retries = int(os.getenv("OLLAMA_RETRIES", "2"))
        delay_seconds = float(os.getenv("OLLAMA_RETRY_DELAY_SECONDS", "0.5"))
        timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

        for attempt in range(retries + 1):
            try:
                response = requests.post(url, json=payload, timeout=timeout_seconds)
                response.raise_for_status()
                return response
            except requests.exceptions.ConnectionError as exc:
                if attempt >= retries:
                    raise ConnectionError(
                        f"Could not connect to Ollama at {url}. "
                        "Please ensure Ollama is running and accessible."
                    ) from exc
            except requests.exceptions.HTTPError as exc:
                if attempt >= retries:
                    raise RuntimeError(f"Ollama returned an error: {exc}") from exc

            sleep_seconds = delay_seconds * (2**attempt)
            print(
                f"[WARN] Ollama request failed for attempt {attempt + 1}. "
                f"Retrying in {sleep_seconds:.2f}s..."
            )
            time.sleep(sleep_seconds)

    def main_loop(
        self,
        progress_callback: Callable[[str, str, int, int], None] | None = None,
        reset_json: bool = True,
    ):
        if reset_json:
            self._json = {}

        # self.type_check_all()
        total_fields = len(self._target_fields.keys())
        for index, field in enumerate(self._target_fields.keys(), start=1):
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

            response = self._post_to_ollama_with_retry(ollama_url, payload)

            # parse response
            json_data = response.json()
            parsed_response = json_data["response"]
            # print(parsed_response)
            self.add_response_to_json(field, parsed_response)

            if progress_callback is not None:
                progress_callback(field, parsed_response, index, total_fields)

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
            values[i] = values[i].lstrip()

        print(f"\t[LOG]: Resulting formatted list of values: {values}")

        return values

    def get_data(self):
        return self._json
