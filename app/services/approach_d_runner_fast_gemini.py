import json
from pathlib import Path
import requests

# Persistent session for connection reuse
session = requests.Session()


def approach_d_runner(narrative: str, target_json: str) -> dict:
    # Minify schema to reduce prompt tokens
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


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2]
    datasets_dir = base_dir / "benchmark" / "datasets"

    narrative_path = datasets_dir / "narratives" / "ics201_1.txt"
    target_json_path = datasets_dir / "templates" / "ics_201.json"

    with open(narrative_path, "r", encoding="utf-8") as f:
        narrative_content = f.read()

    with open(target_json_path, "r", encoding="utf-8") as f:
        target_json_content = f.read()

    result = approach_d_runner(narrative_content, target_json_content)
    print("Extracted JSON Output:")
    print(json.dumps(result, indent=2))
