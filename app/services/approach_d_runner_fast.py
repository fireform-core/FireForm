import json
from pathlib import Path
import requests


def approach_d_runner(narrative: str, target_json: str):
    prompt = """
    You are a precise data extraction engine. Extract information from the provided incident narrative and format it as a valid JSON object strictly adhering to the specified JSON Schema structure and field types. Do not include introductory text, explanations, or Markdown boilerplate—return ONLY the raw JSON object.
    User Prompt:
    Read the following incident narrative and complete the JSON object based on the given target schema.
    Story:
    """
    whole_prompt = prompt + narrative + "\nTarget JSON Schema:\nJSON\n" + target_json

    payload = {
        "model": "qwen2.5:1.5b",
        "prompt": whole_prompt,
        "format": "json",
        "stream": False,
    }

    response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
    response.raise_for_status()

    json_data = response.json() 
    response_str = json_data.get("response", "{}")

    try:
        extracted_json = json.loads(response_str)
    except json.JSONDecodeError:
        extracted_json = {}

    return extracted_json


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