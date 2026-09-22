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
from app.services.approach_d import ApproachD

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2]
    datasets_dir = base_dir / "benchmark" / "datasets"

    narrative_path = datasets_dir / "narratives" / "ics201_10.txt"
    target_json_path = datasets_dir / "templates" / "ics_201.json"
    ground_truth_path = datasets_dir / "ground_truth" / "ics201_10.json"


    with open(narrative_path, "r", encoding="utf-8") as f:
        narrative_content = f.read()

    with open(target_json_path, "r", encoding="utf-8") as f:
        target_json_content = f.read()

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        ground_truth_dict = json.load(f)

    result = ApproachD.fill_form(narrative_content, target_json_content)
    print("Extracted JSON Output:")
    print(json.dumps(result, indent=2))

    # Validator area
    # Unwrap outer wrapper key if present (e.g. "ics201_10_ground_truth")
    if len(ground_truth_dict) == 1 and isinstance(list(ground_truth_dict.values())[0], dict):
        ground_truth_dict = list(ground_truth_dict.values())[0]

    is_same_structure = JSONValidator.json_shape_validator_with_log(result, ground_truth_dict)
    print("Is same structure?:", is_same_structure)

    if is_same_structure:
        print("\n--- Value Accuracy Evaluation ---")
        accuracy_score = AccuracyCalculator.calculate_accuracy(result, ground_truth_dict, verbose=True, use_llm_judge=True, judge_model="qwen2.5:1.5b")
        print(f"\nOverall Value Accuracy Score: {accuracy_score:.2%}")
    else:
        print("\nSkipping accuracy calculation because JSON structure does not match.")


