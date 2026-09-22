import json
import sys
from pathlib import Path
import requests

# Add project root to sys.path so 'benchmark' and 'app' packages can be imported when run directly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.evaluators.JSONValidator import JSONValidator
from benchmark.evaluators.accuracy_calculator import AccuracyCalculator

# Persistent session for connection reuse
session = requests.Session()


def approach_d_runner(narrative: str, target_json_str: str) -> dict:
    target_json : dict = json.loads(target_json_str)

    prompt = (
        "Extract incident details from narrative into the specified JSON structure. "
        "Return ONLY the raw JSON object adhering strictly to the schema types.\n"
        f"Narrative:\n{narrative}\n"
        f"Target JSON Schema:\n{target_json}"
    )

    payload = {
        "model": "qwen2.5:1.5b",
        "prompt": prompt,
        "format": target_json,
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

    narrative_path = datasets_dir / "narratives" / "ics202_5.txt"
    target_json_path = datasets_dir / "templates" / "ics_202.json"
    ground_truth_path = datasets_dir / "ground_truth" / "ics202_5.json"


    with open(narrative_path, "r", encoding="utf-8") as f:
        narrative_content = f.read()

    with open(target_json_path, "r", encoding="utf-8") as f:
        target_json_content = f.read()

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        ground_truth_dict = json.load(f)

    result = approach_d_runner(narrative_content, target_json_content)
    print("Extracted JSON Output:")
    print(json.dumps(result, indent=2))

    # Validator area
    is_same_structure = JSONValidator.json_shape_validator_with_log(result, ground_truth_dict)
    print("Is same structure?:", is_same_structure)

    if is_same_structure:
        print("\n--- Value Accuracy Evaluation ---")
        accuracy_score = AccuracyCalculator.calculate_accuracy(result, ground_truth_dict, verbose=True)
        print(f"\nOverall Value Accuracy Score: {accuracy_score:.2%}")
    else:
        print("\nSkipping accuracy calculation because JSON structure does not match.")


