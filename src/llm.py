import json
import os
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# Ollama HTTP API: transient failures and explicit timeouts
OLLAMA_REQUEST_TIMEOUT = 10
OLLAMA_MAX_ATTEMPTS = 5
_RETRYABLE_HTTP_STATUSES = frozenset({500, 502, 503, 504})


def _should_retry_ollama(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        if resp is not None and resp.status_code in _RETRYABLE_HTTP_STATUSES:
            return True
    return False


class LLM:
    """
    Drives field-by-field extraction via the Ollama `/api/generate` endpoint.

    Network calls use explicit timeouts, exponential backoff retries (up to
    OLLAMA_MAX_ATTEMPTS) for connection errors, timeouts, and HTTP 5xx responses
    (500, 502, 503, 504). Other HTTP errors fail immediately. Parsed values are
    merged with `add_response_to_json` only after a successful response body parse.
    """

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

    @retry(
        stop=stop_after_attempt(OLLAMA_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception(_should_retry_ollama),
        reraise=True,
    )
    def _post_ollama_generate(self, ollama_url: str, payload: dict) -> requests.Response:
        response = requests.post(
            ollama_url,
            json=payload,
            timeout=OLLAMA_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response

    def main_loop(self):
        """
        For each target field, call Ollama with retries on transient failures,
        a bounded request timeout, and strict parsing before updating `_json`.

        On failure, raises ConnectionError for unreachable hosts, RuntimeError for
        timeouts and HTTP errors (with status in the message), or RuntimeError for
        invalid JSON or missing `response` content—without calling
        `add_response_to_json` for that field.
        """
        # self.type_check_all()
        for field in self._target_fields.keys():
            prompt = self.build_prompt(field)
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_url = f"{ollama_host}/api/generate"

            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False,  # don't really know why --> look into this later.
            }

            try:
                response = self._post_ollama_generate(ollama_url, payload)
            except requests.exceptions.ConnectionError as e:
                raise ConnectionError(
                    f"Could not connect to Ollama at {ollama_url} after "
                    f"{OLLAMA_MAX_ATTEMPTS} attempt(s). "
                    "Please ensure Ollama is running and accessible."
                ) from e
            except requests.exceptions.Timeout as e:
                raise RuntimeError(
                    f"Ollama connection timed out after {OLLAMA_REQUEST_TIMEOUT}s "
                    f"(url: {ollama_url}). The service may be overloaded or hung."
                ) from e
            except requests.exceptions.HTTPError as e:
                resp = getattr(e, "response", None)
                if resp is not None:
                    code = resp.status_code
                    reason = (getattr(resp, "reason", None) or "").strip()
                    reason_part = f" {reason}" if reason else ""
                    raise RuntimeError(
                        f"Ollama returned HTTP {code}{reason_part} for {ollama_url}"
                    ) from e
                raise RuntimeError(
                    f"Ollama returned an HTTP error for {ollama_url}: {e}"
                ) from e

            try:
                json_data = response.json()
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"Ollama returned invalid JSON at {ollama_url}: {e}"
                ) from e

            if "response" not in json_data:
                raise RuntimeError(
                    f"Ollama JSON response missing 'response' key at {ollama_url}. "
                    f"Keys present: {list(json_data.keys())}"
                )

            parsed_response = json_data["response"]
            if not isinstance(parsed_response, str):
                raise RuntimeError(
                    f"Ollama 'response' field must be a string at {ollama_url}, "
                    f"got {type(parsed_response).__name__}"
                )

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

    def get_data(self):
        return self._json
