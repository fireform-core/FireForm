import json
import requests

session = requests.Session()

class ApproachD:
    def __init__(self):
        pass

    @staticmethod
    def fill_form(narrative: str, target_json: str, pdf_path: str, output_pdf_path: str):
        try:
            minified_schema = json.dumps(json.loads(target_json), separators=(",", ":"))
        except Exception:
            minified_schema = target_json

        prompt = (
            "Extract incident details from narrative into the specified JSON structure. "
            "Return ONLY the raw JSON object adhering strictly to the schema types.\n"
            f"Narrative:\n{narrative}\n"
            f"Target JSON Schema:\n{minified_schema}"
        )

        payload = {
            "model": "qwen2.5:0.5b",  # or "qwen2.5:0.5b" for maximum speed
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096,
            },
            "keep_alive": "15m",
        }

        response = session.post("http://localhost:11434/api/generate", json=payload, timeout=120)
        response.raise_for_status()

        response_str = response.json().get("response", "{}")

        try:
            return json.loads(response_str)
        except json.JSONDecodeError:
            return {}