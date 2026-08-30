"""Live benchmark test.

Calls a running FireForm API — skipped unless RUN_LIVE_BENCHMARK=1.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from benchmark.pipelines.pipeline import Pipeline
from benchmark.runners.runner import Runner


pytestmark = [
    pytest.mark.live_benchmark,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_BENCHMARK") != "1",
        reason="set RUN_LIVE_BENCHMARK=1 to run the live API benchmark",
    ),
]


def test_pipeline_execution():
    cases = os.getenv("BENCHMARK_CASES", "ics201_1")
    report = Runner(Pipeline, "test-run").run_benchmark(cases)

    out = Path(__file__).parent / "reports"
    out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps(report, indent=2) + "\n")

    metrics = report["metrics"]
    assert metrics["completed_cases"] > 0
    assert metrics["failed_cases"] == 0

    if minimum := os.getenv("BENCHMARK_MIN_ACCURACY"):
        assert metrics["average_accuracy"] >= float(minimum)
