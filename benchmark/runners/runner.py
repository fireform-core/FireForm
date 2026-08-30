from __future__ import annotations

import fnmatch
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark.evaluators.accuracy import calculate_accuracy


CORE_SECTIONS = {
    "incident",
    "dispatch",
    "location",
    "actions_taken",
    "responding_agencies",
    "units",
    "situation_status",
}
BACKGROUND_SECTIONS = {
    "resources_summary",
    "risk_reduction",
    "periodic_reporting",
}


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    narrative_path: Path
    ground_truth_path: Path
    template_path: Path
    pdf_path: Path


def _form_name(case_id: str) -> str:
    base = case_id.split("_", 1)[0]
    if base.startswith("ics") and "_" not in base:
        return f"ics_{base[3:]}"
    return base


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


class Runner:
    def __init__(self, pipeline_class, pipeline_name: str, datasets_dir: str | Path | None = None):
        self.pipeline_class = pipeline_class
        self.pipeline_name = pipeline_name
        self.datasets_dir = Path(datasets_dir or Path(__file__).parents[1] / "datasets")

    def discover_cases(self, selection: str) -> list[BenchmarkCase]:
        narratives_dir = self.datasets_dir / "narratives"
        ground_truth_dir = self.datasets_dir / "updated_ground_truth"
        templates_dir = self.datasets_dir / "updated_templates"
        pdfs_dir = self.datasets_dir / "pdfs"

        if not narratives_dir.is_dir():
            raise ValueError(f"Narratives directory does not exist: {narratives_dir}")

        patterns = [p.strip() for p in selection.split(",") if p.strip()]
        cases: list[BenchmarkCase] = []
        for narrative_path in sorted(narratives_dir.glob("*.txt")):
            case_id = narrative_path.stem
            if selection.casefold() not in {"all", "all-ready"}:
                if not any(fnmatch.fnmatchcase(case_id, p) for p in patterns):
                    continue

            form_name = _form_name(case_id)
            gt = ground_truth_dir / f"{case_id}.json"
            template = templates_dir / f"{form_name}.json"
            pdf = pdfs_dir / f"{form_name}.pdf"

            if not all(p.is_file() for p in (gt, template, pdf)):
                if selection.casefold() == "all-ready":
                    continue
                missing = [n for n, p in {"ground_truth": gt, "template": template, "pdf": pdf}.items() if not p.is_file()]
                raise ValueError(f"Case {case_id} is missing: {', '.join(missing)}")

            cases.append(BenchmarkCase(case_id=case_id, narrative_path=narrative_path,
                                       ground_truth_path=gt, template_path=template, pdf_path=pdf))

        if not cases:
            raise ValueError(f"No benchmark cases matched {selection!r} in {narratives_dir}")
        return cases

    def run_benchmark(self, selection: str = "ics201_1") -> dict[str, Any]:
        cases = self.discover_cases(selection)
        started_at = datetime.now(timezone.utc)
        wall_start = time.monotonic()
        results: list[dict[str, Any]] = []

        print(f"[benchmark] START pipeline={self.pipeline_name} cases={len(cases)}", flush=True)

        for i, case in enumerate(cases, 1):
            print(f"[benchmark {i}/{len(cases)}] START case={case.case_id}", flush=True)
            t0 = time.monotonic()
            try:
                narrative = case.narrative_path.read_text(encoding="utf-8")
                template = json.loads(case.template_path.read_text(encoding="utf-8"))
                output = self.pipeline_class().run(narrative, template, str(case.pdf_path))
                latency = time.monotonic() - t0

                ground_truth = json.loads(case.ground_truth_path.read_text(encoding="utf-8"))
                accuracy = calculate_accuracy(output.extracted_fields, ground_truth)

                section_scores = {
                    section: calculate_accuracy(output.extracted_fields.get(section), expected)
                    for section, expected in ground_truth.items()
                }
                core = [s for name, s in section_scores.items() if name in CORE_SECTIONS]
                background = [s for name, s in section_scores.items() if name in BACKGROUND_SECTIONS]
                metadata = [s for name, s in section_scores.items() if name not in CORE_SECTIONS | BACKGROUND_SECTIONS]

                results.append({
                    "case_id": case.case_id,
                    "status": "completed",
                    "latency_seconds": latency,
                    "accuracy_score": accuracy,
                    "core_accuracy": _average(core),
                    "background_accuracy": _average(background),
                    "metadata_accuracy": _average(metadata),
                    "section_scores": section_scores,
                    "extracted_fields": output.extracted_fields,
                    "ground_truth": ground_truth,
                })
                print(f"[benchmark {i}/{len(cases)}] DONE case={case.case_id} "
                      f"accuracy={accuracy:.3f} latency={latency:.1f}s", flush=True)

            except Exception as exc:
                latency = time.monotonic() - t0
                print(f"[benchmark {i}/{len(cases)}] FAIL case={case.case_id} "
                      f"error={type(exc).__name__}: {exc}", flush=True)
                results.append({
                    "case_id": case.case_id,
                    "status": "failed",
                    "latency_seconds": latency,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                })

        wall_time = time.monotonic() - wall_start
        completed = [r for r in results if r["status"] == "completed"]
        failed = [r for r in results if r["status"] == "failed"]
        accuracies = [r["accuracy_score"] for r in completed]

        print(f"[benchmark] DONE completed={len(completed)} failed={len(failed)} "
              f"avg_accuracy={_average(accuracies) or 'n/a'} wall={wall_time:.1f}s", flush=True)

        return {
            "pipeline_name": self.pipeline_name,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "configuration": {"selection": selection},
            "metrics": {
                "selected_cases": len(cases),
                "completed_cases": len(completed),
                "failed_cases": len(failed),
                "average_accuracy": _average(accuracies),
                "wall_clock_seconds": wall_time,
            },
            "results": results,
        }
