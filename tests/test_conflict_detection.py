from src.batch_orchestrator import BatchOrchestrator
from src.conflict_detector import ConflictCandidate, ConflictDetector


def test_conflict_detector_selects_direct_over_alias_and_default():
    candidates = [
        ConflictCandidate(
            source_id="template_default",
            method="default",
            value="LOW",
            confidence=0.5,
        ),
        ConflictCandidate(
            source_id="incident_record",
            method="inferred_alias",
            value="MEDIUM",
            confidence=0.95,
        ),
        ConflictCandidate(
            source_id="incident_record",
            method="direct",
            value="HIGH",
            confidence=1.0,
        ),
    ]

    selected = ConflictDetector.select_candidate(candidates)
    assert selected is not None
    assert selected.method == "direct"
    assert selected.value == "HIGH"


def test_conflict_detector_returns_none_when_values_match():
    candidates = [
        ConflictCandidate(
            source_id="incident_record",
            method="direct",
            value="INC-9",
            confidence=1.0,
        ),
        ConflictCandidate(
            source_id="incident_record",
            method="inferred_alias",
            value="inc-9",
            confidence=0.95,
        ),
    ]
    selected = ConflictDetector.select_candidate(candidates)
    assert selected is not None

    conflict = ConflictDetector.detect_conflict("incident_id", candidates, selected)
    assert conflict is None


def test_mapping_report_includes_conflict_for_direct_vs_alias_mismatch():
    template_fields = {
        "incident_id": {
            "type": "text",
            "required": True,
            "aliases": ["incident_number"],
        }
    }
    incident_record = {
        "incident_id": "INC-42",
        "incident_number": "INC-43",
    }

    report = BatchOrchestrator._build_mapping_report(template_fields, incident_record)

    assert "conflicts" in report
    assert len(report["conflicts"]) == 1
    conflict = report["conflicts"][0]
    assert conflict["field_name"] == "incident_id"
    assert conflict["selected_method"] == "direct"
    assert conflict["selected_value"] == "INC-42"
