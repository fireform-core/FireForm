import json
import os
import sys


def main():
    if len(sys.argv) < 3:
        print("Usage: python compare_benchmarks.py <branch_report.json> <target_report.json>")
        sys.exit(1)

    branch_file = sys.argv[1]
    target_file = sys.argv[2]

    if not os.path.exists(branch_file) or not os.path.exists(target_file):
        print(f"Error: One or both files do not exist: {branch_file}, {target_file}")
        sys.exit(1)

    with open(branch_file, "r") as f:
        branch_data = json.load(f)

    with open(target_file, "r") as f:
        target_data = json.load(f)

    b_metrics = branch_data.get("metrics", {})
    t_metrics = target_data.get("metrics", {})

    b_acc = b_metrics.get("average_accuracy", 0.0)
    t_acc = t_metrics.get("average_accuracy", 0.0)

    b_lat = b_metrics.get("total_latency_seconds", 0.0)
    t_lat = t_metrics.get("total_latency_seconds", 0.0)

    # Format Markdown comparison
    markdown = f"""
## Pipeline Benchmark Comparison Report

| Metric | Target Branch ({target_data.get('pipeline_name', 'Unknown')}) | PR Branch ({branch_data.get('pipeline_name', 'Unknown')}) | Difference |
|---|---|---|---|
| **Average Accuracy** | {t_acc:.2%} | {b_acc:.2%} | {b_acc - t_acc:+.2%} |
| **Total Latency** | {t_lat:.2f}s | {b_lat:.2f}s | {b_lat - t_lat:+.2f}s |
"""
    print(markdown)

if __name__ == "__main__":
    main()
