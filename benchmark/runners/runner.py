import json
import os
import time

from benchmark.evaluators.JSONValidator import JSONValidator
from benchmark.evaluators.accuracy_calculator import AccuracyCalculator


class Runner:
    def __init__(self, pipeline_class, pipeline_name: str, verbose: bool | None = None):
        self.pipeline = pipeline_class()
        self.pipeline_name = pipeline_name
        if verbose is not None:
            self.verbose = verbose
        else:
            self.verbose = os.getenv("BENCHMARK_VERBOSE", "0").lower() in ("1", "true", "yes")

    def run_benchmark(self) -> dict[str, any]:
        datasets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets")
        narratives_dir = os.path.join(datasets_dir, "narratives")
        ground_truth_dir = os.path.join(datasets_dir, "ground_truth")
        templates_dir = os.path.join(datasets_dir, "templates")
        pdfs_dir = os.path.join(datasets_dir, "pdfs")

        results = []
        total_latency = 0.0

        # Scan narratives directory to find matching ground_truth and template files
        narrative_files = sorted([f for f in os.listdir(narratives_dir) if f.endswith(".txt")])
        total_cases = len(narrative_files)

        print(f"\n{'='*70}\n🚀 Starting Benchmark Evaluation: {self.pipeline_name}\nTotal Test Cases: {total_cases}\n{'='*70}\n")

        for idx, narrative_file in enumerate(narrative_files, start=1):
            case_name = os.path.splitext(narrative_file)[0]
            # Match ics201_1.txt -> ics201_1.json or ics201.json
            possible_gts = [case_name + ".json", case_name.split("_")[0] + "_1.json"]
            gt_file = None
            for p in possible_gts:
                if os.path.exists(os.path.join(ground_truth_dir, p)):
                    gt_file = p
                    break

            # Find matching template file (e.g. ics201_1 -> ics_201.json)
            base_form_name = case_name.split("_")[0]
            if "ics" in base_form_name and "_" not in base_form_name:
                base_form_name = "ics_" + base_form_name[3:]
            template_file = f"{base_form_name}.json"

            narrative_path = os.path.join(narratives_dir, narrative_file)
            gt_path = os.path.join(ground_truth_dir, gt_file) if gt_file else ""
            template_path = os.path.join(templates_dir, template_file)
            pdf_path = os.path.join(pdfs_dir, template_file.replace(".json", ".pdf"))

            if not os.path.exists(gt_path) or not os.path.exists(template_path) or not os.path.exists(pdf_path):
                print(f"[{idx}/{total_cases}] ⚠️  Skipping {case_name}: missing gt/template/pdf")
                continue

            with open(narrative_path, "r", encoding="utf-8") as f:
                narrative_text = f.read()

            with open(gt_path, "r", encoding="utf-8") as f:
                gt_data = json.load(f)
                # Unwrap outer wrapper key if present (e.g. "ics_202_ground_truth")
                if len(gt_data) == 1 and isinstance(list(gt_data.values())[0], dict) and ("ground_truth" in list(gt_data.keys())[0] or "ics" in list(gt_data.keys())[0].lower()):
                    gt_content = list(gt_data.values())[0]
                else:
                    gt_content = gt_data

            with open(template_path, "r", encoding="utf-8") as f:
                template_schema = f.read()

            # Format case_name e.g. ics201_1 -> ics_201_1
            formatted_case_name = case_name
            if "ics" in case_name and not case_name.startswith("ics_"):
                formatted_case_name = "ics_" + case_name[3:]
            output_pdf_path = os.path.join(pdfs_dir, f"{formatted_case_name}_filled.pdf")

            print(f"\n[{idx}/{total_cases}] 📋 Running: '{case_name}' ({base_form_name})...")
            start_time = time.time()
            output = self.pipeline.run(narrative_text, template_schema, pdf_path, output_pdf_path)
            latency = time.time() - start_time
            total_latency += latency

            # 1. Structure Validation
            is_same_structure = JSONValidator.json_shape_validator_with_log(
                output.extracted_fields, gt_content, verbose=self.verbose
            )
            print(f"Is same structure?: {is_same_structure}")

            # 2. Value Accuracy Evaluation (triggered only on structural match)
            if is_same_structure:
                if self.verbose:
                    print("\n--- Value Accuracy Evaluation ---")
                accuracy = AccuracyCalculator.calculate_accuracy(
                    output.extracted_fields,
                    gt_content,
                    verbose=self.verbose,
                    use_llm_judge=True,
                    judge_model="qwen2.5:1.5b",
                )
            else:
                if self.verbose:
                    print(f"\n❌ Skipping value accuracy calculation for '{case_name}' due to structural mismatch.")
                accuracy = 0.0

            print(f"[{idx}/{total_cases}] Finished '{case_name}' | Latency: {latency:.2f}s | Structure Valid: {is_same_structure} | Accuracy: {accuracy * 100:.2f}%\n" + "-" * 70)

            results.append({
                "case_id": case_name,
                "latency_seconds": latency,
                "is_same_structure": is_same_structure,
                "accuracy_score": accuracy,
                "extracted_fields": output.extracted_fields,
                "ground_truth": gt_content
            })

        evaluated_count = len(results)
        matched_structure_count = sum(1 for r in results if r["is_same_structure"])
        avg_accuracy = sum(r["accuracy_score"] for r in results) / evaluated_count if evaluated_count else 0.0
        structure_rate = matched_structure_count / evaluated_count if evaluated_count else 0.0
        avg_latency = total_latency / evaluated_count if evaluated_count else 0.0

        print(f"\n{'='*70}\n📊 Benchmark Summary for {self.pipeline_name}:\n"
              f"  - Total Evaluated Cases: {evaluated_count}\n"
              f"  - Structure Valid Rate: {structure_rate:.2%} ({matched_structure_count}/{evaluated_count})\n"
              f"  - Average Accuracy: {avg_accuracy:.2%}\n"
              f"  - Total Latency: {total_latency:.2f}s (Avg: {avg_latency:.2f}s/case)\n{'='*70}\n")

        return {
            "pipeline_name": self.pipeline_name,
            "metrics": {
                "total_cases": evaluated_count,
                "structure_valid_cases": matched_structure_count,
                "structure_valid_rate": structure_rate,
                "average_accuracy": avg_accuracy,
                "total_latency_seconds": total_latency,
                "average_latency_seconds": avg_latency,
            },
            "results": results
        }
