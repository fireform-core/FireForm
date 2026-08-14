import json
import os
import time

from benchmark.evaluators.accuracy import calculate_accuracy


class Runner:
    def __init__(self, pipeline_class, pipeline_name: str):
        self.pipeline = pipeline_class()
        self.pipeline_name = pipeline_name

    def run_benchmark(self) -> dict[str, any]:
        datasets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets")
        narratives_dir = os.path.join(datasets_dir, "narratives")
        ground_truth_dir = os.path.join(datasets_dir, "ground_truth")
        templates_dir = os.path.join(datasets_dir, "templates")
        pdfs_dir = os.path.join(templates_dir, "pdfs")

        results = []
        total_latency = 0.0

        # Scan narratives directory to find matching ground_truth and template files
        narrative_files = [f for f in os.listdir(narratives_dir) if f.endswith(".txt")]

        for narrative_file in sorted(narrative_files):
            case_name = os.path.splitext(narrative_file)[0]
            # Match ics201_1.txt -> ics201_1.json or ics201.json
            # Find matching ground truth file
            gt_name = case_name.split("_")[0] + "_1.json"  # default fallback
            possible_gts = [case_name + ".json", case_name.split("_")[0] + "_1.json"]
            gt_file = None
            for p in possible_gts:
                if os.path.exists(os.path.join(ground_truth_dir, p)):
                    gt_file = p
                    break

            # Find matching template file
            # e.g., ics201_1 -> ics_201.json
            base_form_name = case_name.split("_")[0]
            # convert ics201 to ics_201 if needed
            if "ics" in base_form_name and "_" not in base_form_name:
                base_form_name = "ics_" + base_form_name[3:]
            template_file = f"{base_form_name}.json"

            narrative_path = os.path.join(narratives_dir, narrative_file)
            gt_path = os.path.join(ground_truth_dir, gt_file) if gt_file else ""
            template_path = os.path.join(templates_dir, template_file)
            pdf_path = os.path.join(pdfs_dir, template_file.replace(".json", ".pdf"))

            if not os.path.exists(gt_path) or not os.path.exists(template_path) or not os.path.exists(pdf_path):
                continue

            with open(narrative_path, "r") as f:
                narrative_text = f.read()

            with open(gt_path, "r") as f:
                gt_data = json.load(f)
                # Unwrap the outer wrapper key if present
                gt_key = list(gt_data.keys())[0]
                gt_content = gt_data[gt_key]

            with open(template_path, "r") as f:
                template_schema = json.load(f)

            start_time = time.time()
            output = self.pipeline.run(narrative_text, template_schema, pdf_path)
            latency = time.time() - start_time
            total_latency += latency

            accuracy = calculate_accuracy(output.extracted_fields, gt_content)

            results.append({
                "case_id": case_name,
                "latency_seconds": latency,
                "accuracy_score": accuracy,
                "extracted_fields": output.extracted_fields,
                "ground_truth": gt_content
            })

        avg_accuracy = sum(r["accuracy_score"] for r in results) / len(results) if results else 0.0

        return {
            "pipeline_name": self.pipeline_name,
            "metrics": {
                "total_latency_seconds": total_latency,
                "average_accuracy": avg_accuracy
            },
            "results": results
        }
