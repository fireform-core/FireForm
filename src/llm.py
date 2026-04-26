import json
import os
import re
import requests
from requests.exceptions import Timeout, RequestException

from src.logger import setup_logger
logger = setup_logger(__name__)


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None):
        if json is None:
            json = {}
        self._transcript_text = transcript_text
        self._target_fields = target_fields
        self._json = json

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
        timeout = 30
        max_retries = 3

        # self.type_check_all()
        total_fields = len(self._target_fields)
        for i, field in enumerate(self._target_fields.keys(), 1):
            prompt = self.build_prompt(field)
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
                        logger.warning(f"Ollama request timed out (attempt {attempt+1})")
                    except RequestException as e:
                        logger.error(f"Ollama request failed: {e}")
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
                logger.info(f"[{i}/{total_fields}] Extracted data for field '{field}' successfully.")

        # ── NEW: build confidence-scored result ──
        extraction_result = self.build_extraction_result()
        logger.info("----------------------------------")
        logger.info("Resulting JSON with confidence scores:")
        logger.info(json.dumps(extraction_result, indent=2))
        logger.info("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field, value):
        """
        Adds the value under the specified field.
        Existing PR #337 fix preserved — handles non-list fields safely.
        """
        value = value.strip().replace('"', "")
        parsed_value = None

        if value != "-1":
            parsed_value = value

        if ";" in value:
            parsed_value = self.handle_plural_values(value)

        if field in self._json:
            if isinstance(self._json[field], list):
                self._json[field].append(parsed_value)
            else:
                self._json[field] = [self._json[field], parsed_value]
        else:
            self._json[field] = parsed_value

        return

    def handle_plural_values(self, plural_value):
        if ";" not in plural_value:
            raise ValueError(
                f"Value is not plural, doesn't have ; separator, Value: {plural_value}"
            )

        logger.info(f"Formatting plural values for JSON, input: {plural_value}")
        values = plural_value.split(";")

        for i in range(len(values)):
            values[i] = values[i].lstrip()

        logger.info(f"Resulting formatted list of values: {values}")
        return values

    def _compute_field_confidence(self, value) -> float:
        """
        Heuristic confidence scoring for an extracted field value.
        Returns a float between 0.0 and 1.0.
        """
        if value is None or value == "" or value == "-1":
            return 0.0
        if isinstance(value, list):
            return 0.85 if len(value) > 0 else 0.0
        if isinstance(value, str):
            vague_patterns = [
                r"not (specified|mentioned|provided|found|available)",
                r"^n/?a$",
                r"^\?+$",
                r"^unknown$"
            ]
            for pattern in vague_patterns:
                if re.search(pattern, value.strip(), re.IGNORECASE):
                    return 0.2
            if len(value.strip()) < 3:
                return 0.3
            return 0.9
        return 0.8

    def build_extraction_result(self) -> dict:
        """
        Wraps each extracted field with a confidence score.
        Adds top-level _meta block with requires_review flag
        when any field confidence is below threshold.
        """
        CONFIDENCE_THRESHOLD = 0.5
        result = {}
        low_confidence_fields = []

        for field, value in self._json.items():
            score = self._compute_field_confidence(value)
            result[field] = {
                "value": value,
                "confidence": round(score, 2)
            }
            if score < CONFIDENCE_THRESHOLD:
                low_confidence_fields.append(field)

        total_fields = len(self._json)
        overall = (
            round(sum(result[f]["confidence"] for f in result) / total_fields, 2)
            if total_fields > 0 else 0.0
        )

        result["_meta"] = {
            "requires_review": len(low_confidence_fields) > 0,
            "low_confidence_fields": low_confidence_fields,
            "overall_confidence": overall
        }

        if result["_meta"]["requires_review"]:
            logger.warning(
                "Extraction requires human review. Low confidence fields: %s",
                low_confidence_fields
            )
        else:
            logger.info("Extraction complete. All fields passed confidence threshold.")

        return result

    def get_data(self):
        return self._json