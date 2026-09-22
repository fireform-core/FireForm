import json
import time
import requests

session = requests.Session()

class ApproachD:
    def __init__(self):
        pass

    @staticmethod
    def fill_form(narrative: str, target_json: str, pdf_path: str, output_pdf_path: str):
        # 1. Parse target_json into a schema dictionary
        try:
            minified_schema = json.loads(target_json) if isinstance(target_json, str) else target_json
        except Exception:
            minified_schema = "json"

        # print(minified_schema)

        prompt = (
            "Extract incident details from narrative into the specified JSON structure. "
            "Return ONLY the raw JSON object adhering strictly to the schema types.\n"
            f"Narrative:\n{narrative}\n"
            f"Target JSON Schema:\n{minified_schema}"
        )

        payload = {
            "model": "qwen2.5:1.5b",
            "prompt": prompt,
            "format": minified_schema,  # <--- Pass the JSON schema dict here instead of "json"
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096,
            },
            "keep_alive": "15m",
        }

        response_str = "{}"
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = session.post("http://localhost:11434/api/generate", json=payload, timeout=120)
                response.raise_for_status()
                response_str = response.json().get("response", "{}")

                print(response_str)
                break
            except (requests.exceptions.RequestException, Exception) as e:
                print(f"Request failed. Attempt {attempt}/{max_retries}.")
                if attempt == max_retries:
                    # Final fallback: try once with generic json format if schema grammar failed
                    print("Final fallback: try once with generic json format if schema grammar failed.")
                    try:
                        fallback_payload = dict(payload, format="json")
                        response = session.post("http://localhost:11434/api/generate", json=fallback_payload, timeout=120)
                        response.raise_for_status()
                        response_str = response.json().get("response", "{}")
                    except Exception:
                        pass
                else:
                    time.sleep(1)

        try:
            return json.loads(response_str)
        except json.JSONDecodeError:
            return {}
