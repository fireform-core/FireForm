"""Tests for the chunked extraction worker (#630).

The model is mocked everywhere: a fake Ollama reads the chunk name out of the
prompt and answers from a canned table, so these cover routing, validation,
retry, failure handling and the deterministic post-steps without a running
Ollama.
"""

import re
from datetime import datetime, timezone

import pytest

from app.api.schemas.enums import ExtractionStatus, InputStatus, InputType
from app.db.repositories import (
    create_extraction,
    create_input,
    create_job,
    get_incident_by_extract,
    get_job_by_uuid,
)
from app.models import Extraction, Input, Job
from app.services.extraction import runner as runner_module
from app.services.llm.errors import (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.extraction.defaults import ExtractionContext, apply_context, resolve_context
from app.services.extraction.prompts import build_prompt, static_prefix
from app.services.extraction.registry import Tier, chunk_registry, extractable_chunks
from app.services.extraction.router import select_chunks
from app.services.extraction.worker import run_extraction

NARRATIVE = (
    "Structure fire at 42 Oak Street in Reno. Engine 12 dispatched, two civilians "
    "injured and transported to hospital. Property loss estimated at 50000. "
    "Investigation points to an electrical cause."
)

# What the fake model answers per chunk. Anything not listed comes back empty,
# which is the honest answer for a chunk the narrative does not support.
ANSWERS = {
    "incident": {
        "name": "Oak Street structure fire",
        "types": [{"category": "fire", "primary": True}],
        "alarm_datetime": "2026-04-18T21:14:00-07:00",
        "first_arrival_datetime": "2026-04-18T21:19:00-07:00",
        "cleared_datetime": "2026-04-18T23:19:00-07:00",
    },
    "location": {"address": "42 Oak Street", "city": "Reno", "state": "NV"},
    "casualties": {"total_civilian_injuries": 2},
    "units": [
        {
            "unit_id": "E12",
            "dispatched_datetime": "2026-04-18T21:14:00-07:00",
            "enroute_datetime": "2026-04-18T21:16:00-07:00",
            "arrived_datetime": "2026-04-18T21:19:00-07:00",
        }
    ],
    "losses": {"property_loss": {"amount": 50000}},
}

_SECTION = re.compile(r"^Section: ([a-z_]+)\.", re.MULTILINE)


def chunk_of(prompt: str) -> str:
    """The chunk a prompt is asking about."""
    match = _SECTION.search(prompt)
    assert match, "every chunk prompt names its section"
    return match.group(1)


def fake_llm(answers=None, calls=None):
    """A stand-in for llm.generate_json that answers from a table."""
    table = ANSWERS if answers is None else answers

    def _call(prompt: str, model: str | None = None, gate=None):
        name = chunk_of(prompt)
        if calls is not None:
            calls.append((name, prompt))
        value = table.get(name, {})
        return {name: value() if callable(value) else value}

    return _call


@pytest.fixture
def mock_llm(monkeypatch):
    """Patch the model call the runner makes. Yields a setter for the answers."""

    def _install(answers=None, calls=None, side_effect=None):
        target = side_effect or fake_llm(answers, calls)
        monkeypatch.setattr(runner_module.llm, "generate_json", target)
        return target

    return _install


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def seed(db, transcript: str = NARRATIVE) -> tuple[Extraction, Job]:
    now = datetime.now(timezone.utc)
    record = create_input(
        db,
        Input(
            input_type=InputType.text,
            status=InputStatus.ready,
            transcript=transcript,
            created_at=now,
            updated_at=now,
        ),
    )
    extraction = create_extraction(
        db,
        Extraction(
            input_id=record.input_id,
            status=ExtractionStatus.processing,
            started_at=now,
            created_at=now,
            updated_at=now,
        ),
    )
    job = create_job(db, Job(celery_task_id="task-1", job_type="extraction", status="queued"))
    return extraction, job


# ---------------------------------------------------------------------------
# Registry and routing
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_every_chunk_carries_a_tier(self):
        registry = chunk_registry()
        assert registry, "the contract should yield chunks"
        assert all(isinstance(spec.tier, Tier) for spec in registry.values())

    def test_manual_chunks_are_never_extracted(self):
        names = {spec.name for spec in extractable_chunks()}
        assert "attachments" not in names
        assert "report_metadata" not in names
        assert "custom_fields" not in names

    def test_gated_chunks_declare_triggers(self):
        gated = [s for s in chunk_registry().values() if s.tier is Tier.gated]
        assert gated
        assert all(spec.triggers for spec in gated)

    def test_list_chunks_are_flagged(self):
        assert chunk_registry()["units"].is_list is True
        assert chunk_registry()["incident"].is_list is False


class TestRouter:
    def test_core_chunks_always_run(self):
        selected = {spec.name for spec in select_chunks("nothing much happened")}
        assert {"incident", "dispatch", "location", "units"} <= selected

    def test_gated_chunk_runs_only_on_evidence(self):
        without = {spec.name for spec in select_chunks("Assisted a resident with a lift.")}
        with_evidence = {spec.name for spec in select_chunks("Brush fire burned four hectares.")}
        assert "wildland" not in without
        assert "wildland" in with_evidence

    def test_core_chunks_come_before_gated(self):
        tiers = [spec.tier for spec in select_chunks(NARRATIVE)]
        assert tiers == sorted(tiers, key=lambda t: [Tier.core, Tier.gated, Tier.background].index(t))


class TestPrompts:
    def test_prefix_is_identical_across_incidents(self):
        spec = chunk_registry()["casualties"]
        first = build_prompt(spec, "one narrative", ["context"])
        second = build_prompt(spec, "a different narrative", ["context"])
        prefix = static_prefix(spec.name, spec.model, spec.is_list, spec.description)
        assert first.startswith(prefix) and second.startswith(prefix)

    def test_narrative_sits_at_the_end(self):
        spec = chunk_registry()["incident"]
        prompt = build_prompt(spec, NARRATIVE, ["context line"])
        assert prompt.rstrip().endswith(NARRATIVE)

    def test_enum_values_are_spelled_out(self):
        spec = chunk_registry()["incident"]
        prompt = build_prompt(spec, NARRATIVE, [])
        assert "hazardous_conditions" in prompt


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_extraction_completes_and_writes_a_draft_incident(self, db, mock_llm):
        mock_llm()
        extraction, job = seed(db)

        result = run_extraction(db, extraction.extract_id, job.job_id)

        assert result["status"] == "completed"
        assert extraction.status == ExtractionStatus.completed
        assert extraction.completed_at is not None
        assert extraction.processing_time_seconds is not None
        # The incident row owns the document, so the working copy is cleared.
        assert extraction.partial_result is None

        incident = get_incident_by_extract(db, extraction.extract_id)
        assert incident is not None
        contract = incident.incident_contract
        assert contract["location"]["city"] == "Reno"
        assert contract["incident"]["name"] == "Oak Street structure fire"
        assert contract["schema_name"] == "fireform_incident_contract"

    def test_promoted_columns_are_recomputed_from_the_contract(self, db, mock_llm):
        mock_llm()
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        incident = get_incident_by_extract(db, extraction.extract_id)
        assert incident.city == "Reno"
        assert incident.state == "NV"
        assert incident.civilian_injuries == 2
        assert incident.incident_category == "fire"
        assert incident.total_loss_amount == 50000
        assert incident.call_to_arrival_seconds == 300
        assert incident.on_scene_duration_seconds == 7200

    def test_job_finishes(self, db, mock_llm):
        mock_llm()
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        stored = get_job_by_uuid(db, job.job_id)
        assert stored.status == "completed"
        assert stored.progress_percent == 100
        assert stored.result_url.endswith(str(extraction.extract_id))

    def test_only_routed_chunks_are_asked_about(self, db, mock_llm):
        calls: list[tuple[str, str]] = []
        mock_llm(calls=calls)
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        asked = {name for name, _ in calls}
        assert "casualties" in asked
        assert "wildland" not in asked

    def test_metadata_records_the_run(self, db, mock_llm):
        mock_llm()
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        contract = get_incident_by_extract(db, extraction.extract_id).incident_contract
        metadata = contract["extraction_metadata"]
        assert metadata["extract_id"] == str(extraction.extract_id)
        assert metadata["llm_model"]
        assert 0 <= metadata["completeness"]["overall_percent"] <= 100


class TestRetryAndFailure:
    def test_a_rejected_answer_is_retried_once(self, db, mock_llm):
        attempts = {"casualties": 0}

        def answers_with_one_miss():
            attempts["casualties"] += 1
            if attempts["casualties"] == 1:
                return {"total_civilian_injuries": "two civilians"}
            return {"total_civilian_injuries": 2}

        calls: list[tuple[str, str]] = []
        mock_llm({**ANSWERS, "casualties": answers_with_one_miss}, calls=calls)
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        assert attempts["casualties"] == 2
        retry_prompt = [p for name, p in calls if name == "casualties"][1]
        assert "previous answer was rejected" in retry_prompt
        contract = get_incident_by_extract(db, extraction.extract_id).incident_contract
        assert contract["casualties"]["total_civilian_injuries"] == 2

    def test_a_bad_field_is_dropped_and_the_rest_of_the_chunk_kept(self, db, mock_llm):
        # One invented enum in a sub-field used to cost the whole section.
        broken = {
            **ANSWERS,
            "losses": {
                "property_loss": {"amount": 50000, "currency": "USD"},
                "estimate_method": "a wild guess",
            },
        }
        mock_llm(broken)
        extraction, job = seed(db)

        result = run_extraction(db, extraction.extract_id, job.job_id)

        assert result["status"] == "completed"
        assert "losses" not in result["failed_chunks"]
        contract = get_incident_by_extract(db, extraction.extract_id).incident_contract
        assert contract["losses"]["property_loss"]["amount"] == 50000
        assert "estimate_method" not in contract["losses"]
        assert "losses.estimate_method" in contract["extraction_metadata"]["completeness"]["missing_fields"]

    def test_salvage_keeps_the_right_list_entries(self, db, mock_llm):
        # Two bad entries in one list: deleting them must not shift the good one.
        units = {
            **ANSWERS,
            "units": [
                {"unit_id": "E12", "response_mode": "warp_speed"},
                {"unit_id": "E13"},
                {"unit_id": "E14", "response_mode": "teleport"},
            ],
        }
        mock_llm(units)
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        stored = get_incident_by_extract(db, extraction.extract_id).incident_contract["units"]
        assert [unit["unit_id"] for unit in stored] == ["E12", "E13", "E14"]
        assert all("response_mode" not in unit for unit in stored)

    def test_a_chunk_with_nothing_salvageable_is_left_empty(self, db, mock_llm):
        # Its only field is unusable, so what survives the salvage pass is empty.
        mock_llm({**ANSWERS, "casualties": {"total_civilian_injuries": "loads"}})
        extraction, job = seed(db)

        result = run_extraction(db, extraction.extract_id, job.job_id)

        assert result["status"] == "completed"
        contract = get_incident_by_extract(db, extraction.extract_id).incident_contract
        assert "casualties" not in contract
        missing = contract["extraction_metadata"]["completeness"]["missing_fields"]
        assert "casualties" in missing
        assert "casualties.total_civilian_injuries" in missing

    def test_an_unusable_chunk_shape_is_reported_as_failed(self, db, mock_llm):
        # A scalar where the section's object belongs: there is nothing to keep.
        def scalar_casualties(prompt, model=None, gate=None):
            name = chunk_of(prompt)
            return {name: "two people hurt" if name == "casualties" else ANSWERS.get(name, {})}

        mock_llm(side_effect=scalar_casualties)
        extraction, job = seed(db)

        result = run_extraction(db, extraction.extract_id, job.job_id)

        assert result["status"] == "completed"
        assert "casualties" in result["failed_chunks"]
        assert "casualties" not in get_incident_by_extract(db, extraction.extract_id).incident_contract

    def test_a_timed_out_chunk_is_not_retried(self, db, mock_llm):
        calls: list[str] = []

        def slow_casualties(prompt, model=None, gate=None):
            name = chunk_of(prompt)
            calls.append(name)
            if name == "casualties":
                raise LLMTimeoutError("the provider did not answer within 300s")
            return {name: ANSWERS.get(name, {})}

        mock_llm(side_effect=slow_casualties)
        extraction, job = seed(db)

        result = run_extraction(db, extraction.extract_id, job.job_id)

        # One attempt only: the same prompt on the same model takes the same time.
        assert calls.count("casualties") == 1
        assert "casualties" in result["failed_chunks"]
        assert extraction.status == ExtractionStatus.completed

    def test_run_fails_when_every_chunk_is_rejected(self, db, mock_llm):
        def always_broken(prompt, model=None, gate=None):
            # A scalar where the chunk's object belongs: rejected every time.
            return {chunk_of(prompt): "not an object"}

        mock_llm(side_effect=always_broken)
        extraction, job = seed(db)

        result = run_extraction(db, extraction.extract_id, job.job_id)

        assert result["status"] == "failed"
        assert extraction.status == ExtractionStatus.failed
        assert extraction.error_type == "EXTRACTION_FAILED"
        assert get_incident_by_extract(db, extraction.extract_id) is None
        assert get_job_by_uuid(db, job.job_id).status == "failed"

    def test_ollama_down_fails_the_run(self, db, mock_llm):
        def unreachable(prompt, model=None, gate=None):
            raise LLMUnavailableError("could not reach Ollama at http://ollama:11434")

        mock_llm(side_effect=unreachable)
        extraction, job = seed(db)

        with pytest.raises(LLMUnavailableError):
            run_extraction(db, extraction.extract_id, job.job_id)

        assert extraction.status == ExtractionStatus.failed
        assert extraction.error_type == "LLM_UNAVAILABLE"
        assert "could not reach Ollama" in extraction.error_detail
        assert get_job_by_uuid(db, job.job_id).error["error_code"] == "LLM_UNAVAILABLE"

    def test_a_rate_limited_run_fails_but_keeps_what_it_had(self, db, mock_llm):
        """A quota that will not lift stops the run. It does not erase it."""
        later = next(spec.name for spec in select_chunks(NARRATIVE) if spec.tier is not Tier.core)

        def rate_limited(prompt, model=None, gate=None):
            name = chunk_of(prompt)
            if name == later:
                raise LLMRateLimitError("still rate limiting after 11 attempts", 10.0)
            return {name: ANSWERS.get(name, {})}

        mock_llm(side_effect=rate_limited)
        extraction, job = seed(db)

        result = run_extraction(db, extraction.extract_id, job.job_id)

        assert result["status"] == "failed"
        assert result["retry_after_seconds"] == 10.0
        assert extraction.status == ExtractionStatus.failed
        assert extraction.error_type == "LLM_RATE_LIMITED"
        assert extraction.partial_result["incident"]["name"]
        assert get_job_by_uuid(db, job.job_id).error["error_code"] == "LLM_RATE_LIMITED"

    def test_empty_transcript_fails_before_any_call(self, db, mock_llm):
        calls: list[tuple[str, str]] = []
        mock_llm(calls=calls)
        extraction, job = seed(db, transcript="   ")

        result = run_extraction(db, extraction.extract_id, job.job_id)

        assert result["status"] == "failed"
        assert extraction.error_type == "EMPTY_INPUT"
        assert calls == []

    def test_a_missing_extraction_is_a_no_op(self, db, mock_llm):
        from uuid import uuid4

        mock_llm()
        assert run_extraction(db, uuid4(), "job-does-not-exist")["status"] == "missing"


# ---------------------------------------------------------------------------
# Deterministic post-steps
# ---------------------------------------------------------------------------

class TestDeterministicSteps:
    def test_request_defaults_win_over_config(self):
        context = resolve_context({"country": "IN", "timezone": "Asia/Kolkata", "currency": "INR"})
        assert (context.country, context.timezone, context.currency) == ("IN", "Asia/Kolkata", "INR")

    def test_unknown_timezone_falls_back_to_utc(self):
        context = resolve_context({"timezone": "Mars/Olympus"})
        assert str(context.zone) == "UTC"

    def test_defaults_fill_country_currency_and_offset(self):
        context = ExtractionContext(
            country="IN",
            timezone="Asia/Kolkata",
            currency="INR",
            now=datetime.now(timezone.utc),
        )
        filled = apply_context(
            {
                "location": {"city": "Pune"},
                "losses": {"property_loss": {"amount": 1200}},
                "incident": {"alarm_datetime": "2026-04-18T21:14:00"},
            },
            context,
        )
        assert filled["location"]["country"] == "IN"
        assert filled["losses"]["property_loss"]["currency"] == "INR"
        assert filled["incident"]["alarm_datetime"].endswith("+05:30")
        assert filled["incident"]["timezone"] == "Asia/Kolkata"

    def test_blank_answers_are_dropped_but_zero_is_kept(self):
        context = ExtractionContext("US", "UTC", "USD", datetime.now(timezone.utc))
        filled = apply_context(
            {
                "incident": {"name": "", "special_modifiers": [], "chimney_fire": False},
                "casualties": {"total_civilian_injuries": 0},
                "structure": {"floors": {"above_grade": ""}},
            },
            context,
        )
        assert "name" not in filled["incident"]
        assert "special_modifiers" not in filled["incident"]
        assert filled["incident"]["chimney_fire"] is False
        assert filled["casualties"]["total_civilian_injuries"] == 0
        assert "structure" not in filled

    def test_currency_already_stated_is_left_alone(self):
        context = ExtractionContext("US", "UTC", "USD", datetime.now(timezone.utc))
        filled = apply_context({"losses": {"property_loss": {"amount": 10, "currency": "GBP"}}}, context)
        assert filled["losses"]["property_loss"]["currency"] == "GBP"

    def test_unit_turnout_and_travel_are_computed(self, db, mock_llm):
        mock_llm()
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        unit = get_incident_by_extract(db, extraction.extract_id).incident_contract["units"][0]
        assert unit["turnout_seconds"] == 120
        assert unit["travel_seconds"] == 180

    def test_computed_timings_beat_a_stated_duration(self, db, mock_llm):
        # Models do state a duration that contradicts the times they just gave.
        stated = {**ANSWERS, "units": [{**ANSWERS["units"][0], "turnout_seconds": 570}]}
        mock_llm(stated)
        extraction, job = seed(db)
        run_extraction(db, extraction.extract_id, job.job_id)

        unit = get_incident_by_extract(db, extraction.extract_id).incident_contract["units"][0]
        assert unit["turnout_seconds"] == 120

    def test_a_stated_duration_survives_when_there_is_nothing_to_compute(self):
        context = ExtractionContext("US", "UTC", "USD", datetime.now(timezone.utc))
        filled = apply_context({"units": [{"unit_id": "E12", "turnout_seconds": 95}]}, context)
        assert filled["units"][0]["turnout_seconds"] == 95
