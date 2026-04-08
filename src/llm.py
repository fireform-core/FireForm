import json
import os
import requests


class LLM:
    CONFIDENCE_THRESHOLD = 0.85

    def __init__(self, transcript_text=None, target_fields=None, json=None):
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List, contains the template field.
        self._json = json  # dictionary: confirmed fields (confidence >= threshold)
        self._needs_review = {}  # fields with low confidence that a human must verify

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
        Returns a structured JSON object with value and confidence so that downstream logic can apply
        a human-in-the-loop review for hallucinated or low-confidence fields.
        @params: current_field -> represents the current element of the json that is being prompted.
        """
        prompt = f"""
            SYSTEM PROMPT:
            You are an AI assistant designed to help fill out JSON files with information extracted from transcribed voice recordings.
            You will receive the transcription and the name of the JSON field whose value you must identify.

            You MUST respond with a single valid JSON object and nothing else. The JSON must have exactly two keys:
            - "value": the identified string value for the field, or null if not found.
            - "confidence": a float between 0.0 and 1.0 representing how certain you are.

            Rules:
            - If the field is plural and you find multiple values, separate them with ";" in the value string.
            - If you cannot find the value, set "value" to null and "confidence" to 0.0.
            - Do NOT add any explanation or text outside the JSON object.

            Example output: {{"value": "John Doe", "confidence": 0.95}}
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

            # parse raw Ollama response
            json_data = response.json()
            raw_text = json_data["response"].strip()
            self.add_response_to_json(field, raw_text)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field, raw_text):
        """
        Parses the structured JSON response from the LLM.
        Confirmed fields (confidence >= CONFIDENCE_THRESHOLD) go into self._json.
        Low-confidence fields go into self._needs_review for human verification.
        """
        import json as json_lib
        value = None
        confidence = 0.0

        try:
            # The LLM is prompted to always return a JSON object
            parsed = json_lib.loads(raw_text)
            value = parsed.get("value")
            confidence = float(parsed.get("confidence", 0.0))
        except (json_lib.JSONDecodeError, ValueError, TypeError):
            # If the LLM failed to return valid JSON, treat the whole text as a
            # low-confidence raw string so it gets flagged for human review.
            print(f"\t[WARN]: LLM returned non-JSON for field '{field}'. Flagging for review.")
            value = raw_text if raw_text not in ("-1", "null", "") else None
            confidence = 0.0

        # Handle plural values (semicolon-separated)
        if value and ";" in str(value):
            value = self.handle_plural_values(value)

        if confidence >= self.CONFIDENCE_THRESHOLD:
            # High-confidence: write directly into the confirmed JSON
            if field in self._json:
                self._json[field].append(value)
            else:
                self._json[field] = value
        else:
            # Low-confidence: flag for human-in-the-loop review
            print(f"\t[REVIEW REQUIRED]: Field '{field}' has confidence {confidence:.2f} (threshold: {self.CONFIDENCE_THRESHOLD}). Value: '{value}'")
            self._needs_review[field] = {
                "suggested_value": value,
                "confidence": confidence,
            }

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
        """Returns confirmed high-confidence field values."""
        return self._json

    def get_needs_review(self):
        """Returns fields that could not be extracted with sufficient confidence and require human review."""
        return self._needs_review
