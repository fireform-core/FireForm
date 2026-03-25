from dataclasses import dataclass
from typing import Any


@dataclass
class ConflictCandidate:
    source_id: str
    method: str
    value: Any
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "method": self.method,
            "value": self.value,
            "confidence": self.confidence,
        }


@dataclass
class ConflictRecord:
    field_name: str
    candidates: list[ConflictCandidate]
    selected_source: str
    selected_value: Any
    selected_method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selected_source": self.selected_source,
            "selected_value": self.selected_value,
            "selected_method": self.selected_method,
        }


class ConflictDetector:
    _PRIORITY = {
        "direct": 3,
        "inferred_alias": 2,
        "default": 1,
        "none": 0,
    }

    @classmethod
    def select_candidate(cls, candidates: list[ConflictCandidate]) -> ConflictCandidate | None:
        if not candidates:
            return None

        return max(
            candidates,
            key=lambda candidate: (cls._PRIORITY.get(candidate.method, 0), candidate.confidence),
        )

    @classmethod
    def detect_conflict(
        cls,
        field_name: str,
        candidates: list[ConflictCandidate],
        selected: ConflictCandidate,
    ) -> ConflictRecord | None:
        comparable_values = {
            cls._normalize_value(candidate.value)
            for candidate in candidates
            if candidate.value is not None and str(candidate.value).strip() != ""
        }

        if len(comparable_values) <= 1:
            return None

        return ConflictRecord(
            field_name=field_name,
            candidates=candidates,
            selected_source=selected.source_id,
            selected_value=selected.value,
            selected_method=selected.method,
        )

    @staticmethod
    def _normalize_value(value: Any) -> str:
        return str(value).strip().lower()
