# FireForm Extraction Pipeline Benchmarking Suite

This module contains the infrastructure to evaluate and compare different extraction pipelines across branches.

## Structure
- `/datasets/`: Contains the evaluation narratives, ground truth JSON outputs, and form template schema descriptors.
- `/evaluators/`: Defines custom comparison metrics (fuzzy matching, exact matching).
- `/runners/`: Executable scripts to run pipelines against datasets.
- `test_benchmark.py`: Pytest suite to run the evaluation dynamically on whichever pipeline is checked out.
- `compare_benchmarks.py`: Tool to format a markdown diff report comparing two output JSON report files.

## Running Locally
Install test requirements:
```bash
pip install pytest
```

Execute the local benchmark:
```bash
pytest benchmark/test_benchmark.py -v -s
```
This produces `benchmark/benchmark_report.json` containing metrics (accuracy, latency) and full result logs.
