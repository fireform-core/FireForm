import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from zipfile import ZIP_DEFLATED, ZipFile

from src.conflict_detector import ConflictCandidate, ConflictDetector
from src.evidence_model import FieldEvidenceReport


@dataclass
class BatchTemplateResult:
    template_id: int
    template_name: str
    status: str
    output_pdf_path: str | None
    error: str | None
    mapping_report: dict[str, Any]


class BatchOrchestrator:
    def __init__(
        self,
        fill_single_form_fn: Callable[[str, dict[str, Any], dict[str, Any]], str],
    ):
        self.fill_single_form_fn = fill_single_form_fn

    def run_batch(
        self,
        incident_record: dict[str, Any],
        templates: list[Any],
        output_root: str = "src/outputs/batches",
    ) -> dict[str, Any]:
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        output_dir = os.path.join(output_root, batch_id)
        os.makedirs(output_dir, exist_ok=True)

        results: list[BatchTemplateResult] = []
        successful_outputs: list[str] = []

        for template in templates:
            template_fields = self._normalize_template_fields(getattr(template, "fields", {}))
            mapping_report = self._build_mapping_report(template_fields, incident_record)

            if not mapping_report["compatible"]:
                results.append(
                    BatchTemplateResult(
                        template_id=template.id,
                        template_name=template.name,
                        status="failed_validation",
                        output_pdf_path=None,
                        error="Compatibility validation failed",
                        mapping_report=mapping_report,
                    )
                )
                continue

            try:
                output_pdf_path = self.fill_single_form_fn(
                    template.pdf_path,
                    incident_record,
                    template_fields,
                )
                successful_outputs.append(output_pdf_path)
                results.append(
                    BatchTemplateResult(
                        template_id=template.id,
                        template_name=template.name,
                        status="success",
                        output_pdf_path=output_pdf_path,
                        error=None,
                        mapping_report=mapping_report,
                    )
                )
            except Exception as exc:
                results.append(
                    BatchTemplateResult(
                        template_id=template.id,
                        template_name=template.name,
                        status="failed_runtime",
                        output_pdf_path=None,
                        error=str(exc),
                        mapping_report=mapping_report,
                    )
                )

        report_payload = {
            "batch_id": batch_id,
            "created_at": datetime.now().isoformat(),
            "total_templates": len(templates),
            "successful_count": len([r for r in results if r.status == "success"]),
            "failed_count": len([r for r in results if r.status != "success"]),
            "results": [
                {
                    "template_id": r.template_id,
                    "template_name": r.template_name,
                    "status": r.status,
                    "output_pdf_path": r.output_pdf_path,
                    "error": r.error,
                    "mapping_report": r.mapping_report,
                }
                for r in results
            ],
        }

        report_json_path = os.path.join(output_dir, "batch_report.json")
        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(report_payload, f, indent=2)

        zip_path = os.path.join(output_root, f"{batch_id}.zip")
        self._build_batch_zip(zip_path, successful_outputs, report_json_path)

        report_payload["package_zip_path"] = zip_path
        return report_payload

    @staticmethod
    def _build_batch_zip(
        zip_path: str,
        successful_outputs: list[str],
        report_json_path: str,
    ) -> None:
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zip_file:
            for output_file in successful_outputs:
                if os.path.exists(output_file):
                    zip_file.write(output_file, arcname=os.path.basename(output_file))
            zip_file.write(report_json_path, arcname="batch_report.json")

    @staticmethod
    def _normalize_template_fields(fields: Any) -> dict[str, Any]:
        if isinstance(fields, dict):
            return fields
        if isinstance(fields, list):
            return {str(field): "text" for field in fields}
        return {}

    @staticmethod
    def _build_mapping_report(
        template_fields: dict[str, Any],
        incident_record: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_record = {
            BatchOrchestrator._normalize_key(str(k)): v for k, v in incident_record.items()
        }
        normalized_to_original = {
            BatchOrchestrator._normalize_key(str(k)): str(k) for k in incident_record.keys()
        }

        missing_fields: set[str] = set()
        matched_fields: set[str] = set()
        type_mismatches: dict[str, str] = {}
        field_evidence: dict[str, FieldEvidenceReport] = {}
        conflicts: list[dict[str, Any]] = []

        normalized_template_tokens: set[str] = set()

        for field_name, field_meta in template_fields.items():
            aliases = BatchOrchestrator._infer_aliases(field_meta)
            candidate_names = [field_name, *aliases]
            candidate_tokens = [BatchOrchestrator._normalize_key(name) for name in candidate_names]
            normalized_template_tokens.update(candidate_tokens)

            direct_token = BatchOrchestrator._normalize_key(field_name)
            raw_candidates: list[ConflictCandidate] = []

            if direct_token in normalized_record:
                raw_candidates.append(
                    ConflictCandidate(
                        source_id="incident_record",
                        method="direct",
                        value=normalized_record[direct_token],
                        confidence=1.0,
                    )
                )

            for alias in aliases:
                alias_token = BatchOrchestrator._normalize_key(alias)
                if alias_token in normalized_record:
                    raw_candidates.append(
                        ConflictCandidate(
                            source_id="incident_record",
                            method="inferred_alias",
                            value=normalized_record[alias_token],
                            confidence=0.95,
                        )
                    )

            if isinstance(field_meta, dict) and "default" in field_meta:
                raw_candidates.append(
                    ConflictCandidate(
                        source_id="template_default",
                        method="default",
                        value=field_meta.get("default"),
                        confidence=0.5,
                    )
                )

            selected_candidate = ConflictDetector.select_candidate(raw_candidates)
            matched_key = direct_token if direct_token in normalized_record else None
            if matched_key is None and selected_candidate and selected_candidate.method == "inferred_alias":
                matched_key = next(
                    (
                        BatchOrchestrator._normalize_key(alias)
                        for alias in aliases
                        if BatchOrchestrator._normalize_key(alias) in normalized_record
                    ),
                    None,
                )

            required = BatchOrchestrator._infer_required(field_meta)
            if selected_candidate is None:
                if required:
                    missing_fields.add(field_name)
                # Record evidence for unmatched field
                field_evidence[field_name] = FieldEvidenceReport(
                    field_name=field_name,
                    matched=False,
                    source_id="none",
                    method="none",
                    confidence=0.0,
                    evidence_count=0,
                )
                continue

            matched_fields.add(field_name)
            expected_type = BatchOrchestrator._infer_field_type(field_meta)
            value = selected_candidate.value
            issue = BatchOrchestrator._validate_value_type(expected_type, value)
            if issue:
                type_mismatches[field_name] = issue

            # Record evidence for matched field
            field_evidence[field_name] = FieldEvidenceReport(
                field_name=field_name,
                matched=True,
                source_id=selected_candidate.source_id,
                method=selected_candidate.method,
                confidence=selected_candidate.confidence,
                evidence_count=len(raw_candidates),
            )

            conflict = ConflictDetector.detect_conflict(
                field_name=field_name,
                candidates=raw_candidates,
                selected=selected_candidate,
            )
            if conflict:
                conflicts.append(conflict.to_dict())

        extra_fields = {
            original
            for token, original in normalized_to_original.items()
            if token not in normalized_template_tokens
        }

        warnings = []
        if extra_fields:
            warnings.append(f"Found {len(extra_fields)} field(s) not in template schema")
        if type_mismatches:
            warnings.append(f"Found {len(type_mismatches)} type mismatch(es)")

        compatible = not missing_fields and not type_mismatches

        return {
            "compatible": compatible,
            "missing_fields": sorted(missing_fields),
            "extra_fields": sorted(extra_fields),
            "unmapped_fields": sorted(extra_fields),
            "type_mismatches": type_mismatches,
            "dependency_violations": [],
            "warnings": warnings,
            "matched_fields": sorted(matched_fields),
            "conflicts": conflicts,
            "field_evidence": {
                field_name: evidence.model_dump()
                for field_name, evidence in field_evidence.items()
            },
        }

    @staticmethod
    def _infer_field_type(field_meta: Any) -> str:
        if isinstance(field_meta, dict):
            raw_type = str(field_meta.get("type", "text")).lower()
        else:
            raw_type = str(field_meta).lower()

        if raw_type in {"email"}:
            return "email"
        if raw_type in {"phone", "tel", "telephone"}:
            return "phone"
        if raw_type in {"date", "datetime"}:
            return "date"
        if raw_type in {"number", "int", "float", "integer"}:
            return "number"
        if raw_type in {"checkbox", "bool", "boolean"}:
            return "checkbox"
        if raw_type in {"dropdown", "select", "choice"}:
            return "dropdown"
        return "text"

    @staticmethod
    def _infer_required(field_meta: Any) -> bool:
        if isinstance(field_meta, dict):
            return bool(field_meta.get("required", False))
        return False

    @staticmethod
    def _infer_aliases(field_meta: Any) -> list[str]:
        if isinstance(field_meta, dict):
            aliases = field_meta.get("aliases", [])
            if isinstance(aliases, list):
                return [str(alias) for alias in aliases]
        return []

    @staticmethod
    def _normalize_key(value: str) -> str:
        return "".join(ch.lower() for ch in value if ch.isalnum())

    @staticmethod
    def _validate_value_type(expected_type: str, value: Any) -> str | None:
        value_str = str(value).strip()

        if expected_type == "email":
            if "@" not in value_str or "." not in value_str.split("@")[-1]:
                return f"Invalid email format: {value}"

        if expected_type == "phone":
            digits = "".join(ch for ch in value_str if ch.isdigit())
            if len(digits) < 7:
                return f"Invalid phone format (need 7+ digits): {value}"

        if expected_type == "date":
            date_patterns = [
                r"^\d{1,2}/\d{1,2}/\d{4}$",
                r"^\d{4}-\d{1,2}-\d{1,2}$",
                r"^[A-Za-z]+ \d{1,2}, \d{4}$",
            ]
            if not any(re.match(pattern, value_str) for pattern in date_patterns):
                return f"Invalid date format: {value}"

        if expected_type == "number":
            try:
                float(value_str)
            except ValueError:
                return f"Invalid number: {value}"

        if expected_type == "checkbox":
            valid = {"yes", "no", "true", "false", "1", "0", "checked", "unchecked"}
            if value_str.lower() not in valid:
                return f"Invalid checkbox value: {value}"

        return None