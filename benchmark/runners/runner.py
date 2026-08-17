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
        ground_truth_dir = os.path.join(datasets_dir, "updated_ground_truth")
        templates_dir = os.path.join(datasets_dir, "updated_templates")
        pdfs_dir = os.path.join(datasets_dir, "pdfs")

        results = []
        total_latency = 0.0

        # Scan narratives directory to find matching ground_truth and template files
        narrative_files = [f for f in os.listdir(narratives_dir) if f.endswith(".txt")]
        case_filter = os.getenv("BENCHMARK_CASE")
        if case_filter:
            narrative_files = [
                filename
                for filename in narrative_files
                if os.path.splitext(filename)[0] == case_filter
            ]
            if not narrative_files:
                raise ValueError(f"Unknown BENCHMARK_CASE: {case_filter}")

        total = len(narrative_files)
        for idx, narrative_file in enumerate(sorted(narrative_files), start=1):
            case_name = os.path.splitext(narrative_file)[0]
            gt_file = case_name + ".json"
            base_form_name = case_name.split("_")[0]
            if "ics" in base_form_name and "_" not in base_form_name:
                base_form_name = "ics_" + base_form_name[3:]

            narrative_path = os.path.join(narratives_dir, narrative_file)
            gt_path = os.path.join(ground_truth_dir, gt_file)
            template_path = os.path.join(templates_dir, f"{base_form_name}.json")
            pdf_path = os.path.join(pdfs_dir, f"{base_form_name}.pdf")

            if not all(os.path.exists(path) for path in (gt_path, template_path, pdf_path)):
                continue

            with open(narrative_path, "r") as f:
                narrative_text = f.read()

            with open(gt_path, "r") as f:
                gt_content = json.load(f)

            with open(template_path, "r") as f:
                template_fields = json.load(f)
            template_schema = {name: template_fields[name] for name in gt_content}

            print(f"  [{idx}/{total}] Running {case_name} ...", flush=True)
            start_time = time.time()
            output = self.pipeline.run(narrative_text, template_schema, pdf_path)
            latency = time.time() - start_time
            total_latency += latency

            accuracy = calculate_accuracy(output.extracted_fields, gt_content)
            print(f"  [{idx}/{total}] {case_name} done — latency={latency:.2f}s  accuracy={accuracy:.3f}", flush=True)

            results.append({
                "case_id": case_name,
                "latency_seconds": latency,
                "accuracy_score": accuracy,
                "extracted_fields": output.extracted_fields,
                "ground_truth": gt_content
            })

        print(f"\n[Runner] Iterations completed: {len(results)} / {len(narrative_files)} narratives")

        avg_accuracy = sum(r["accuracy_score"] for r in results) / len(results) if results else 0.0

        return {
            "pipeline_name": self.pipeline_name,
            "metrics": {
                "total_latency_seconds": total_latency,
                "average_accuracy": avg_accuracy
            },
            "results": results
        }
