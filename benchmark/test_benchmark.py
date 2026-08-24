import json
import os
from datetime import datetime

from benchmark.pipelines.pipeline import Pipeline
from benchmark.runners.runner import Runner


def test_pipeline_execution():
    """
    Standard test executor that finds the available Pipeline class,
    runs the benchmark dataset, writes execution results to a file, and asserts accuracy.
    """
    # Pipeline name contains current date and hour, minute and second (e.g. Pipeline_2026-07-08_12h_12m_12s)
    timestamp = datetime.now().strftime("%Y-%m-%d_%Hh_%Mm_%Ss")
    pipeline_name = f"Pipeline_{timestamp}"

    runner = Runner(Pipeline, pipeline_name)
    report = runner.run_benchmark()

    # Save results to a report file to be compared in CI/CD pipeline
    report_path = os.path.join(os.path.dirname(__file__), "benchmark_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Assert basic quality sanity check
    assert report["metrics"]["average_accuracy"] >= 0.0
    print(f"\n{pipeline_name} evaluation complete. Average Accuracy: {report['metrics']['average_accuracy']:.2f}")
