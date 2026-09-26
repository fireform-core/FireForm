import json
import os

import requests
from requests.exceptions import RequestException, Timeout

from app.core.config import OLLAMA_HOST, OLLAMA_MODEL
from app.core.logging import get_logger
from app.models.models import Profile

logger = get_logger(__name__)


def append_profile_context(base_prompt: str, profile: Profile = None) -> str:
    if not profile:
        return base_prompt
        
    desc = profile.description if profile.description else "N/A"
        
    profile_context = (
        "=== USER PROFILE CONTEXT ===\n"
        "The form is being filled out by a user with the following profile:\n"
        f"- Name: {profile.name}\n"
        f"- Profession: {profile.profession}\n"
        f"- Role: {profile.role}\n"
        f"- Description: {desc}\n"
    )
    
    if profile.custom_fields:
        for key, value in profile.custom_fields.items():
            profile_context += f"- {key.capitalize()}: {value}\n"
            
    profile_context += "\nPlease use this context to provide more relevant and tailored field suggestions and validations.\n\n"
    return profile_context + base_prompt


class LLM:
    def __init__(self, transcript_text: str=None, target_fields: list=None, json_dict: dict=None, model: str=None, profile: Profile=None):
        self._transcript_text = transcript_text
        self._target_fields = target_fields
        self._json = json_dict if json_dict is not None else {}
        self._model = model
        self._profile = profile
    
    def build_prompt(self, current_field: str, current_type: str = "string"):
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
        # In case prompt.txt isn't in Colab, we'll use a fallback for testing
        try:
            with open(prompt_path, "r") as f:
                template = f.read()
        except FileNotFoundError:
            template = "Extract the {field} ({type}) from the following text:\n{text}"

        base_prompt = template.format(field=current_field, type=current_type, text=self._transcript_text)
        return append_profile_context(base_prompt, self._profile)

    def main_loop(self):
        timeout = 45
        max_retries = 3

        total_fields = len(self._target_fields)
        for i, (field, field_type) in enumerate(self._target_fields.items(), 1):
            prompt = self.build_prompt(field, field_type if isinstance(field_type, str) else "string")
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
