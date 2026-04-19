import requests
from requests.exceptions import Timeout, RequestException


def call_llm(prompt: str, timeout: int = 30, retries: int = 2):
    payload = {
        "model": "mistral",
        "prompt": prompt,
        "stream": False
    }

    url = "http://localhost:11434/api/generate"

    for attempt in range(retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()

        except Timeout:
            if attempt == retries:
                raise RuntimeError("LLM request timed out")

        except RequestException as e:
            if attempt == retries:
                raise RuntimeError(f"LLM request failed: {e}")

    return None