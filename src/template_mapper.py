"""
TemplateMapper — YAML-driven PDF field mapping engine.

YAML Mapping Spec
-----------------
Each agency form is described by a YAML file placed in the `templates/` directory.
The format is:

    name: "Cal Fire FIRESCOPE"
    pdf_path: "src/inputs/cal_fire_firescope_template.pdf"
    fields:
      - pdf_field_name: "IncidentID"
        json_path: "incident_id"

      - pdf_field_name: "WildfireAcres"
        json_path: "area_burned_acres"
        condition: "incident_type == 'wildfire'"

Field keys:
  pdf_field_name  (required) — exact field name as it appears in the PDF.
  json_path       (required) — dot-separated path into the IncidentReport model.
                               Supports top-level keys only for now (e.g. "supervisor").
  condition       (optional) — boolean expression evaluated against the IncidentReport
                               dict. Field is skipped (left blank) when False.

Supported condition operators:  ==  !=  in  not in  and  or  not
No arbitrary Python is permitted — only Name, Constant, Compare, BoolOp, UnaryOp nodes
are allowed by the evaluator. Any other node raises ValueError.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import yaml

from src.schemas.incident_report import IncidentReport

logger = logging.getLogger(__name__)


class TemplateMapper:
    """
    Loads a YAML agency mapping file and resolves IncidentReport field values
    to the corresponding PDF form field names.

    Usage:
        mapper = TemplateMapper("templates/cal_fire_firescope.yaml")
        field_values = mapper.resolve(incident_report)
        # field_values == {"IncidentID": "CAL-2024-001", "Location": "...", ...}
    """

    def __init__(self, yaml_path: str | Path) -> None:
        self._yaml_path = Path(yaml_path)
        self._config = self._load(self._yaml_path)

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._config["name"]

    @property
    def pdf_path(self) -> str:
        return self._config["pdf_path"]

    def resolve(self, report: IncidentReport) -> dict[str, Any]:
        """
        Walk the YAML field list and resolve each entry against the report.

        Returns a dict of {pdf_field_name: value} for all fields whose
        condition (if any) evaluates to True. Fields with a null/None value
        are mapped to an empty string so the PDF writer does not raise.
        """
        data = report.model_dump(exclude={"requires_review"})
        result: dict[str, Any] = {}

        for field_def in self._config.get("fields", []):
            pdf_field = field_def["pdf_field_name"]
            json_path = field_def["json_path"]
            condition = field_def.get("condition")

            if condition:
                try:
                    if not self._evaluate_condition(condition, data):
                        logger.debug("Skipping field %r — condition %r is False", pdf_field, condition)
                        continue
                except ValueError as exc:
                    logger.warning("Bad condition on field %r: %s — skipping", pdf_field, exc)
                    continue

            value = self._resolve_path(json_path, data)
            result[pdf_field] = self._to_string(value)

        return result

    # -------------------------------------------------------------------------
    # YAML loading
    # -------------------------------------------------------------------------

    def _load(self, path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Template mapping not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        self._validate_config(config, path)
        return config

    def _validate_config(self, config: dict, path: Path) -> None:
        for required in ("name", "pdf_path", "fields"):
            if required not in config:
                raise ValueError(f"YAML template {path} is missing required key: '{required}'")
        for i, field in enumerate(config["fields"]):
            for key in ("pdf_field_name", "json_path"):
                if key not in field:
                    raise ValueError(
                        f"YAML template {path}, field[{i}] is missing required key: '{key}'"
                    )

    # -------------------------------------------------------------------------
    # JSON path resolution
    # -------------------------------------------------------------------------

    def _resolve_path(self, json_path: str, data: dict) -> Any:
        """
        Resolve a dot-separated path against the data dict.
        e.g. "location_city" → data["location_city"]
        Supports top-level keys only for now; returns None for missing paths.
        """
        keys = json_path.split(".")
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if current is None:
                return None
        return current

    @staticmethod
    def _to_string(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    # -------------------------------------------------------------------------
    # Safe condition evaluator  (P2-4)
    # -------------------------------------------------------------------------

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        """
        Safely evaluate a condition expression string against context.

        Only the following AST node types are permitted:
          Compare, BoolOp (and/or), UnaryOp (not), Name, Constant.

        Any other node — including function calls, attribute access, or
        subscripts — raises ValueError, preventing arbitrary code execution.
        """
        try:
            tree = ast.parse(condition, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid condition syntax: {condition!r}") from exc

        return self._eval_node(tree.body, context)

    def _eval_node(self, node: ast.expr, context: dict) -> Any:
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                if isinstance(op, ast.Eq):
                    result = left == right
                elif isinstance(op, ast.NotEq):
                    result = left != right
                elif isinstance(op, ast.In):
                    result = left in right
                elif isinstance(op, ast.NotIn):
                    result = left not in right
                elif isinstance(op, ast.Lt):
                    result = left < right
                elif isinstance(op, ast.LtE):
                    result = left <= right
                elif isinstance(op, ast.Gt):
                    result = left > right
                elif isinstance(op, ast.GtE):
                    result = left >= right
                else:
                    raise ValueError(f"Unsupported operator: {type(op).__name__}")
                if not result:
                    return False
            return True

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._eval_node(v, context) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(self._eval_node(v, context) for v in node.values)

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not self._eval_node(node.operand, context)

        if isinstance(node, ast.Name):
            return context.get(node.id)

        if isinstance(node, ast.Constant):
            return node.value

        raise ValueError(
            f"Expression node type {type(node).__name__!r} is not permitted in conditions. "
            "Only comparisons, boolean operators, field names, and literal values are allowed."
        )
