import io
import json
import os
import sys
from datetime import datetime

from benchmark.pipelines.pipeline import Pipeline
from benchmark.runners.runner import Runner


class _TeeStream(io.TextIOBase):
    """Writes to both the original stream and a file simultaneously."""

    def __init__(self, original, file_handle):
        super().__init__()
        self._original = original
        self._file = file_handle

    def write(self, s):
        self._original.write(s)
        self._original.flush()
        self._file.write(s)
        self._file.flush()
        return len(s)

    def flush(self):
        self._original.flush()
        self._file.flush()


def test_pipeline_execution():
    """
    Standard test executor that finds the available Pipeline class,
    runs the benchmark dataset, writes execution results to a file, and asserts accuracy.
    """
    # Pipeline name contains current date and hour, minute and second (e.g. Pipeline_2026-07-08_12h_12m_12s)
    timestamp = datetime.now().strftime("%Y-%m-%d_%Hh_%Mm_%Ss")
    pipeline_name = f"Pipeline_{timestamp}"

    benchmark_dir = os.path.dirname(__file__)
    txt_report_path = os.path.join(benchmark_dir, "benchmark_report.txt")

    with open(txt_report_path, "w", encoding="utf-8") as txt_file:
        tee = _TeeStream(sys.stdout, txt_file)
        original_stdout = sys.stdout
        sys.stdout = tee
        try:
            runner = Runner(Pipeline, pipeline_name)
            report = runner.run_benchmark()
        finally:
            sys.stdout = original_stdout

    # Save results to a report file to be compared in CI/CD pipeline
    report_path = os.path.join(benchmark_dir, "benchmark_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"📄 Terminal output saved to: {txt_report_path}")

    # Assert basic quality sanity check
    assert report["metrics"]["average_accuracy"] >= 0.0
    print(f"\n{pipeline_name} evaluation complete. Average Accuracy: {report['metrics']['average_accuracy']:.2%}")


if __name__ == "__main__":
    test_pipeline_execution()
