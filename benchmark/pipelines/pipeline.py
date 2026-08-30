import os
import time
from typing import Any

import requests

from app.core.config import API_PREFIX
from benchmark.pipelines.base import BasePipeline, PipelineExtractionOutput


API_ORIGIN = os.getenv(
    "BENCHMARK_API_ORIGIN",
    "http://127.0.0.1:8000",
).rstrip("/")

API_BASE_URL = f"{API_ORIGIN}{API_PREFIX}"

EXTRACTION_TIMEOUT_SECONDS = float(os.getenv("BENCHMARK_EXTRACTION_TIMEOUT_SECONDS", "7200"))
PROGRESS_INTERVAL_SECONDS = max(
    1.0,
    float(os.getenv("BENCHMARK_PROGRESS_INTERVAL_SECONDS", "15")),
)


class ExtractionTimeoutError(TimeoutError):
    def __init__(self, extract_id: str, job_id: str, timeout_seconds: float):
        self.extract_id = extract_id
        self.job_id = job_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Extraction {extract_id} did not complete within {timeout_seconds:.0f} seconds"
        )


def _api(method: str, path: str, **kwargs: Any) -> requests.Response:
    url = f"{API_BASE_URL}{path}"
    try:
        response = requests.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach the FireForm API at {url}: {exc}") from exc

    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"FireForm API returned HTTP {response.status_code} for {method} {path}: {detail}"
        )
    return response


def _build_output(extraction_result: dict[str, Any], latency: float) -> PipelineExtractionOutput:
    contract = extraction_result["incident_contract"]
    metadata = contract.get("extraction_metadata") or {}
    confidence = metadata.get("confidence_score")
    return PipelineExtractionOutput(
        extracted_fields=contract,
        field_confidence={"__overall__": float(confidence)} if confidence is not None else {},
        latency_seconds=latency,
    )


class Pipeline(BasePipeline):

    def recover(self, extract_id: str) -> PipelineExtractionOutput:
        print(f"[pipeline] RECOVER extract_id={extract_id}", flush=True)
        result = _api("GET", f"/extract/{extract_id}").json()
        if result.get("status") != "completed":
            raise RuntimeError(
                f"Extraction {extract_id} cannot be recovered — status is {result.get('status')!r}"
            )
        return _build_output(result, float(result.get("processing_time_seconds") or 0.0))

    def run(
        self,
        narrative: str,
        template_schema: dict,
        pdf_path: str,
    ) -> PipelineExtractionOutput:
        started_at = time.monotonic()
        case_label = os.path.basename(pdf_path)
        log = lambda msg: print(f"[pipeline] {msg}", flush=True)

        log(f"START case={case_label} narrative_chars={len(narrative)} "
            f"template_fields={len(template_schema)}")

        _ = template_schema
        _ = pdf_path

        # 1. Submit narrative.
        log("INPUT submitting narrative")
        input_result = _api("POST", "/input/text", json={"narrative": narrative}).json()
        input_id = input_result["input_id"]
        log(f"INPUT stored input_id={input_id}")

        # 2. Start extraction.
        log("EXTRACTION submitting job")
        extraction_job = _api("POST", f"/extract/{input_id}", json={}).json()
        extract_id = extraction_job["extract_id"]
        job_id = extraction_job["job_id"]
        log(f"EXTRACTION queued extract_id={extract_id} job_id={job_id}")

        # 3. Poll until done.
        deadline = time.monotonic() + EXTRACTION_TIMEOUT_SECONDS
        next_progress_at = 0.0

        while True:
            result = _api("GET", f"/extract/{extract_id}").json()
            status = result["status"]
            now = time.monotonic()

            if now >= next_progress_at:
                elapsed = now - started_at
                progress, job_status = "unknown", "unknown"
                try:
                    job = _api("GET", f"/jobs/{job_id}").json()
                    progress = f"{job.get('progress_percent', 0)}%"
                    job_status = job.get("status", "unknown")
                except RuntimeError as exc:
                    log(f"POLL job progress unavailable: {exc}")
                log(f"POLL extract_status={status} job_status={job_status} "
                    f"progress={progress} elapsed={elapsed:.1f}s")
                next_progress_at = now + PROGRESS_INTERVAL_SECONDS

            if status == "completed":
                latency = now - started_at
                log(f"EXTRACTION completed extract_id={extract_id} elapsed={latency:.1f}s")
                log(f"DONE case={case_label} total_elapsed={latency:.1f}s")
                return _build_output(result, latency)

            if status == "failed":
                error_type = result.get("error_type", "EXTRACTION_FAILED")
                error_detail = result.get("error_detail", "No error detail was returned")
                log(f"EXTRACTION failed extract_id={extract_id} "
                    f"error_type={error_type} detail={error_detail}")
                raise RuntimeError(f"Extraction {extract_id} failed: {error_type}: {error_detail}")

            if now >= deadline:
                log(f"EXTRACTION timeout extract_id={extract_id} "
                    f"limit={EXTRACTION_TIMEOUT_SECONDS:.0f}s")
                raise ExtractionTimeoutError(extract_id, job_id, EXTRACTION_TIMEOUT_SECONDS)

            poll_interval = (
                result.get("retry_after_seconds")
                or extraction_job.get("retry_after_seconds")
                or 5
            )
            time.sleep(float(poll_interval))
