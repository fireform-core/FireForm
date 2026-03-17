import json
import os
import httpx
import logging
from src.core.orchestrator import orchestrator

logger = logging.getLogger(__name__)

class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json_data=None):
        if json_data is None:
            json_data = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List, contains the template field.
        self._json = json_data  # dictionary

    def type_check_all(self):
        if not isinstance(self._transcript_text, str):
            raise TypeError(
                f"ERROR in LLM() attributes -> "
                f"Transcript must be text. Input:\n\ttranscript_text: {self._transcript_text}"
            )
        elif not isinstance(self._target_fields, dict):
            raise TypeError(
                f"ERROR in LLM() attributes -> "
                f"Target fields must be a dictionary. Input:\n\ttarget_fields: {self._target_fields}"
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

    async def main_loop(self):
        # self.type_check_all()
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        async with httpx.AsyncClient() as client:
            for field in self._target_fields.keys():
                prompt = self.build_prompt(field)
                payload = {
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                }

                # VRAM Orchestration: Ensure serial hardware access
                async with orchestrator.lock:
                    try:
                        response = await client.post(ollama_url, json=payload, timeout=60.0)
                        response.raise_for_status()
                        json_data = response.json()
                        parsed_response = json_data["response"]
                        self.add_response_to_json(field, parsed_response)
                    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as e:
                        logger.error(f"Transport error connecting to Ollama at {ollama_url}: {e}")
                        raise ConnectionError(
                            f"Could not connect to Ollama at {ollama_url}. "
                            "Please ensure Ollama is running and accessible."
                        )
                    except httpx.HTTPStatusError as e:
                        logger.error(f"Ollama returned an error: {e}")
                        raise RuntimeError(f"Ollama returned an error: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error during LLM extraction: {e}")
                        raise

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
            # If it's already a list, append. If not, make it a list or just overwrite?
            # Original code used .append() which assumes it's a list.
            if isinstance(self._json[field], list):
                self._json[field].append(parsed_value)
            else:
                self._json[field] = parsed_value # or [self._json[field], parsed_value]
        else:
            self._json[field] = parsed_value

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
        values = [v.strip() for v in plural_value.split(";")]

        print(f"\t[LOG]: Resulting formatted list of values: {values}")

        return values

    def get_data(self):
        return self._json
