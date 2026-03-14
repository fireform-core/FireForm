import json
import os
import requests


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json_data=None):
        if json_data is None:
            json_data = {}

        self._transcript_text = transcript_text
        self._target_fields = target_fields
        self._json = json_data

    def type_check_all(self):
        if type(self._transcript_text) is not str:
            raise TypeError(
                f"Transcript must be text. Received: {self._transcript_text}"
            )

        if type(self._target_fields) is not dict:
            raise TypeError(
                f"Target fields must be a dictionary. Received: {self._target_fields}"
            )

    def build_structured_prompt(self):
        fields = list(self._target_fields.keys())
        schema = "\n".join(fields)

        prompt = f"""
You are an AI system that extracts structured information from incident reports.

Return ONLY valid JSON matching the fields below.

Fields:
{schema}

Text:
{self._transcript_text}
"""

        return prompt

    def main_loop(self):
        self.type_check_all()
        return self.structured_extraction()

    def structured_extraction(self):
        print("[LLM] Running structured extraction")

        prompt = self.build_structured_prompt()

        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        url = f"{ollama_host}/api/generate"

        payload = {
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Could not connect to Ollama at {url}. Ensure Ollama is running."
            )
        except requests.exceptions.Timeout:
            raise RuntimeError("LLM request timed out.")

        result = response.json()["response"].strip()

        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"LLM returned invalid JSON:\n{result}"
            )

        self._json = parsed

        print("----------------------------------")
        print("[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def handle_plural_values(self, plural_value):
        if ";" not in plural_value:
            raise ValueError(
                f"Value does not contain ';' separator: {plural_value}"
            )

        print(
            f"[LOG] Formatting plural values for JSON (input: {plural_value})"
        )

        values = [v.strip() for v in plural_value.split(";")]

        print(f"[LOG] Resulting formatted list: {values}")

        return values

    def get_data(self):
        return self._json