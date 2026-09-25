import json
import time
import requests

session = requests.Session()

# Context window tiers — pick the smallest one that fits the prompt
_CTX_TIERS = [4096, 8192, 16384, 32768]


def _pick_num_ctx(prompt: str) -> int:
    """Estimate token count (chars / 3.5) and pick the smallest sufficient tier."""
    estimated_tokens = int(len(prompt) / 3.5)
    # Leave ~20% headroom for schema grammar + response
    needed = int(estimated_tokens * 1.2)
    for tier in _CTX_TIERS:
        if tier >= needed:
            return tier
    return _CTX_TIERS[-1]


class ApproachD:
    def __init__(self):
        pass

    @staticmethod
    def fill_form(narrative: str, target_json: str, pdf_path: str|None = None, output_pdf_path: str|None = None):
        # 1. Parse target_json into a schema dictionary
        try:
            minified_schema = json.loads(target_json) if isinstance(target_json, str) else target_json
        except Exception:
            minified_schema = "json"

        prompt = (
            "Extract incident details from narrative into the specified JSON structure. "
            "Return ONLY the raw JSON object adhering strictly to the schema types.\n"
            f"Narrative:\n{narrative}\n"
            f"Target JSON Schema:\n{minified_schema}"
        )

        num_ctx = _pick_num_ctx(prompt)
        print(f"[ApproachD] Prompt ~{int(len(prompt)/3.5)} tokens → using num_ctx={num_ctx}")

        payload = {
            "model": "qwen2.5:1.5b",
            "prompt": prompt,
            "format": minified_schema,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": num_ctx,
            },
            "keep_alive": "15m",
        }

        response_str = "{}"
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = session.post("http://localhost:11434/api/generate", json=payload, timeout=35)
                response.raise_for_status()
                response_str = response.json().get("response", "{}")
                break
            except (requests.exceptions.RequestException, Exception) as e:
                print(f"Request failed (attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    # Final fallback: strip schema grammar constraint and try plain JSON mode
                    print("Final fallback: retrying with format='json' (no grammar constraint).")
                    try:
                        fallback_payload = dict(payload, format="json")
                        response = session.post("http://localhost:11434/api/generate", json=fallback_payload, timeout=35)
                        response.raise_for_status()
                        response_str = response.json().get("response", "{}")
                    except Exception as fe:
                        print(f"Final fallback also failed: {fe}")
                else:
                    time.sleep(1)

        try:
            return json.loads(response_str)
        except json.JSONDecodeError:
            return {}

