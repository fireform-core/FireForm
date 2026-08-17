import json
import os

import requests
from requests.exceptions import RequestException, Timeout

from app.core.config import OLLAMA_HOST, OLLAMA_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLM:
    def __init__(self, transcript_text: str=None, target_fields: list=None, json_dict: dict=None, model: str=None):
        self._transcript_text = transcript_text
        self._target_fields = target_fields
        self._json = json_dict if json_dict is not None else {}
        # Optional per-request model override; falls back to OLLAMA_MODEL env.
        self._model = model

    def build_prompt(
        self,
        current_field: str,
        current_type: str = "string",
        description: str = "",
    ):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt for each target field.
        @params: current_field -> represents the current element of the json that is being prompted.
        @params: current_type  -> hint to the LLM about the expected value shape (date, number, etc.).
        """
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
        with open(prompt_path, "r") as f:
            template = f.read()

        return template.format(
            field=current_field,
            type=current_type,
            description=description or current_field,
            text=self._transcript_text,
        )

    def main_loop(self):
        timeout = 45
        max_retries = 3

        total_fields = len(self._target_fields)
        for i, (field, field_definition) in enumerate(self._target_fields.items(), 1):
            if isinstance(field_definition, dict):
                field_type = field_definition.get("field_type", field_definition.get("type", "string"))
                description = field_definition.get("description", field)
            else:
                field_type = field_definition if isinstance(field_definition, str) else "string"
                description = field
            prompt = self.build_prompt(field, field_type, description)
            ollama_url = f"{OLLAMA_HOST}/api/generate"
            ollama_model = self._model or OLLAMA_MODEL

            payload = {
                "model": ollama_model,
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
                        logger.warning("Ollama request timed out (attempt %d) for field '%s'. Retrying...", attempt + 1, field)
                    except RequestException as e:
                        logger.error("Ollama request failed: %s", e)
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
                logger.info("[%d/%d] Extracted data for field '%s' successfully.", i, total_fields, field)

        logger.info("Resulting JSON created from the input text:\n%s", json.dumps(self._json, indent=2))

        return self

    def add_response_to_json(self, field: str, value: str):
        """
        this method adds the following value under the specified field,
        or under a new field if the field doesn't exist, to the json dict
        """
        value = value.strip().replace('"', "")
        parsed_value = None

        if value != "-1":
            parsed_value = value

        if field in self._json.keys():
            self._json[field].append(parsed_value)
        else:
            self._json[field] = parsed_value



    def get_data(self):
        return self._json
