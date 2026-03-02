"""
Schema validation and error recovery for LLM-extracted data.

Validates the JSON output from the LLM against the template's field schema,
flags missing or malformed values, and produces a structured validation report
that can be used for error recovery or user-facing warnings.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------

class Confidence(str, Enum):
    HIGH = "high"       # value found and passes type check
    LOW = "low"         # value found but type coercion was needed
    MISSING = "missing" # value not found in transcript (was null / -1)


# ---------------------------------------------------------------------------
# Per-field result model
# ---------------------------------------------------------------------------

class FieldResult(BaseModel):
    field: str
    value: Any
    confidence: Confidence
    raw_value: Any
    warning: str | None = None


# ---------------------------------------------------------------------------
# Full validation report
# ---------------------------------------------------------------------------

class ValidationReport(BaseModel):
    is_valid: bool
    fields: list[FieldResult]
    warnings: list[str]

    @property
    def missing_fields(self) -> list[str]:
        return [r.field for r in self.fields if r.confidence == Confidence.MISSING]

    @property
    def validated_data(self) -> dict:
        """Return only fields with HIGH or LOW confidence as a plain dict."""
        return {
            r.field: r.value
            for r in self.fields
            if r.confidence != Confidence.MISSING
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class SchemaValidator:
    """
    Validates LLM-extracted JSON against a template field schema.

    Schema format (matches Template.fields in the DB):
        {
            "field_name": "string" | "int" | "float" | "list",
            ...
        }

    Usage::

        validator = SchemaValidator()
        report = validator.validate(extracted_dict, template.fields)
        if not report.is_valid:
            print(report.warnings)
        clean_data = report.validated_data
    """

    _TYPE_MAP: dict[str, type] = {
        "string": str,
        "str":    str,
        "int":    int,
        "float":  float,
        "list":   list,
    }

    def validate(self, extracted: dict, schema: dict) -> ValidationReport:
        """
        Validate *extracted* against *schema*.

        :param extracted: Dict produced by LLM.get_data()
        :param schema:    Dict of {field_name: type_string} from the Template model
        :returns:         A :class:`ValidationReport`
        """
        results: list[FieldResult] = []
        warnings: list[str] = []

        for field_name, type_hint in schema.items():
            raw = extracted.get(field_name)
            expected_type = self._TYPE_MAP.get(str(type_hint).lower(), str)

            # ----------------------------------------------------------------
            # Missing / null
            # ----------------------------------------------------------------
            if raw is None or raw == "-1" or raw == "":
                msg = f"Missing value for required field: '{field_name}'"
                warnings.append(msg)
                results.append(
                    FieldResult(
                        field=field_name,
                        value=None,
                        confidence=Confidence.MISSING,
                        raw_value=raw,
                        warning=msg,
                    )
                )
                continue

            # ----------------------------------------------------------------
            # Type already correct
            # ----------------------------------------------------------------
            if isinstance(raw, expected_type):
                results.append(
                    FieldResult(
                        field=field_name,
                        value=raw,
                        confidence=Confidence.HIGH,
                        raw_value=raw,
                    )
                )
                continue

            # ----------------------------------------------------------------
            # Attempt coercion
            # ----------------------------------------------------------------
            try:
                coerced = expected_type(raw)
                msg = (
                    f"Field '{field_name}': expected {expected_type.__name__}, "
                    f"got {type(raw).__name__} — coerced successfully."
                )
                warnings.append(msg)
                results.append(
                    FieldResult(
                        field=field_name,
                        value=coerced,
                        confidence=Confidence.LOW,
                        raw_value=raw,
                        warning=msg,
                    )
                )
            except (ValueError, TypeError):
                msg = (
                    f"Field '{field_name}': could not coerce value "
                    f"'{raw}' to {expected_type.__name__}. Keeping raw string."
                )
                warnings.append(msg)
                results.append(
                    FieldResult(
                        field=field_name,
                        value=str(raw),
                        confidence=Confidence.LOW,
                        raw_value=raw,
                        warning=msg,
                    )
                )

        missing = [r.field for r in results if r.confidence == Confidence.MISSING]
        return ValidationReport(
            is_valid=len(missing) == 0,
            fields=results,
            warnings=warnings,
        )
