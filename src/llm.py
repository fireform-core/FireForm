import json
import logging
import os
import time
import requests

logger = logging.getLogger("fireform.llm")

# Configuration constants 
LLM_REQUEST_TIMEOUT_SECONDS = 120
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY_SECONDS = 2


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
                f"ERROR in LLM() attributes -> "
                f"Transcript must be text. Input:\n\ttranscript_text: {self._transcript_text}"
            )
        elif type(self._target_fields) is not list:
            raise TypeError(
                f"ERROR in LLM() attributes -> "
                f"Target fields must be a list. Input:\n\ttarget_fields: {self._target_fields}"
            )

    def build_prompt(self, current_field):
        """
        Creates a specific prompt for each target field.
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

    def _call_ollama(self, prompt, field_name):
        """
        Send a prompt to Ollama with timeout and retry logic.
        """
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        payload = {
            "model": "mistral",
            "prompt": prompt,
            "stream": False,
        }

        last_exception = None

        for attempt in range(1, LLM_MAX_RETRIES + 1):
            try:
                logger.info(
                    "LLM request for field '%s' (attempt %d/%d)",
                    field_name,
                    attempt,
                    LLM_MAX_RETRIES,
                )

                response = requests.post(
                    ollama_url,
                    json=payload,
                    timeout=LLM_REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()

                json_data = response.json()
                result = json_data["response"]

                logger.info(
                    "LLM response for field '%s': %s",
                    field_name,
                    result[:100] if len(result) > 100 else result,
                )

                return result

            except requests.exceptions.Timeout as exc:
                last_exception = exc
                logger.warning(
                    "LLM request timed out for field '%s' (attempt %d/%d)",
                    field_name,
                    attempt,
                    LLM_MAX_RETRIES,
                )

            except requests.exceptions.ConnectionError as exc:
                last_exception = exc
                logger.warning(
                    "Cannot connect to Ollama for field '%s' (attempt %d/%d)",
                    field_name,
                    attempt,
                    LLM_MAX_RETRIES,
                )

            except requests.exceptions.HTTPError as exc:
                last_exception = exc
                if response.status_code >= 500:
                    logger.warning(
                        "Ollama server error %d for field '%s' (attempt %d/%d)",
                        response.status_code,
                        field_name,
                        attempt,
                        LLM_MAX_RETRIES,
                    )
                else:
                    # Client errors (4xx) should not be retried
                    raise RuntimeError(
                        f"Ollama returned client error {response.status_code} "
                        f"for field '{field_name}': {exc}"
                    ) from exc

            # Exponential backoff before retry
            if attempt < LLM_MAX_RETRIES:
                delay = LLM_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)

        # All retries exhausted
        raise RuntimeError(
            f"LLM extraction failed for field '{field_name}' after "
            f"{LLM_MAX_RETRIES} attempts: {last_exception}"
        )

    def main_loop(self):
        """
        Iterate over all target fields, extract values from the LLM,
        and build the result JSON.
        """
        logger.info(
            "Starting LLM extraction for %d fields",
            len(self._target_fields) if self._target_fields else 0,
        )

        for field in self._target_fields.keys():
            prompt = self.build_prompt(field)
            parsed_response = self._call_ollama(prompt, field_name=field)
            self.add_response_to_json(field, parsed_response)

        logger.info("LLM extraction complete. Result:\n%s", json.dumps(self._json, indent=2))

        return self

    def add_response_to_json(self, field, value):
        """
        Adds the extracted value under the specified field in the JSON dict.
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
        Handles plural values separated by semicolons.
        'value1; value2; value3' → ['value1', 'value2', 'value3']
        """
        if ";" not in plural_value:
            raise ValueError(
                f"Value is not plural, doesn't have ; separator, Value: {plural_value}"
            )

        logger.debug("Formatting plural values for input: %s", plural_value)
        values = plural_value.split(";")

        for i in range(len(values)):
            current = i + 1
            if current < len(values):
                clean_value = values[current].lstrip()
                values[current] = clean_value

        logger.debug("Resulting formatted list: %s", values)

        return values

    def get_data(self):
        return self._json