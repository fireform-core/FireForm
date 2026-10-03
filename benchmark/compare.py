import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from accuracy import (
    _is_blank,
    _is_empty_value,
    _is_ignored_field,
    _is_unchecked_checkbox,
    calculate_accuracy,
    calculate_accuracy_with_judge,
)


_MISSING = object()
_EXCLUDED = object()


def build_ground_truth_shape(
    json_template: Any,
    ground_truth: Any,
) -> Any:
    """Copy ground-truth content into the shape of ``json_template``.

    The ground-truth values are not changed. Only their container structure is
    changed. This supports, among others, all of these templates for a flat
    ground-truth mapping::

        {"Incident Name": ""}
        {"Incident Name": {"field_value": ""}}
        {"Incident Name": {"Incident Name": {"field_value": ""}}}
        {"p.0_x.0": {"field_name": "Incident Name", "field_value": ""}}

    ``field_name`` is treated as a reference into the flat ground truth and
    ``field_value`` receives the referenced value. Other literal metadata from
    the template (for example ``xref`` or ``field_type``) is preserved.
    """

    def reshape(template: Any, source: Any, inherited: Any = _MISSING) -> Any:
        if isinstance(template, dict):
            # An explicit field_name lets ID-keyed template objects reference
            # the corresponding value in a flat ground-truth mapping.
            explicit_name = template.get("field_name")
            referenced = _MISSING
            if (
                isinstance(explicit_name, str)
                and isinstance(ground_truth, dict)
                and explicit_name in ground_truth
            ):
                referenced = ground_truth[explicit_name]

            context = referenced if referenced is not _MISSING else source
            result = {}
            for key, child_template in template.items():
                if key != "field_value" and referenced is not _MISSING:
                    # In an explicit field descriptor, everything except
                    # field_value is template metadata rather than extracted
                    # ground-truth content.
                    result[key] = child_template
                    continue

                if key == "field_value":
                    value = context if context is not _MISSING else inherited
                    result[key] = (
                        child_template if value is _MISSING else value
                    )
                    continue

                child_source = _MISSING
                if isinstance(source, dict) and key in source:
                    child_source = source[key]
                elif isinstance(ground_truth, dict) and key in ground_truth:
                    child_source = ground_truth[key]

                child_inherited = (
                    context if context is not _MISSING else inherited
                )
                result[key] = reshape(
                    child_template,
                    child_source,
                    child_inherited,
                )
            return result

        if isinstance(template, list):
            result = []
            for index, child_template in enumerate(template):
                child_source = _MISSING
                if isinstance(source, list) and index < len(source):
                    child_source = source[index]
                result.append(reshape(child_template, child_source, inherited))
            return result

        if source is not _MISSING:
            return source
        if inherited is not _MISSING:
            return inherited
        return template

    return reshape(json_template, ground_truth)


def fold_tables(flat: dict, tables: list | None, groups: dict | None) -> dict:
    """Inverse of ``form_filler.template.expand_output``: regroup flat ``Row1..RowN`` widget
    values into lists of row dicts so tables are scored by content, not position."""
    if not tables:
        return flat
    folded = dict(flat)
    for table_num, table in enumerate(tables):
        rows = []
        for row_index in range(table["row_count"]):
            row = {}
            for column in table["columns"]:
                members = groups.get(column, [])
                if row_index < len(members) and members[row_index] in folded:
                    row[column] = folded.pop(members[row_index])
            if row:
                rows.append(row)
        folded[table_name(table, table_num)] = rows
    return folded


def table_name(table: dict, table_num: int) -> str:
    """Schema key of a table; context_template names tables after their caption."""
    return table.get("name", f"resource_summary_{table_num}_table")


def flatten_overrides(
    overrides: dict[str, float], tables: list | None, groups: dict | None
) -> dict[str, float]:
    """Translate judge overrides on folded table cells back to flat widget paths
    so the review PDFs reflect judge decisions."""
    flat = {}
    table_names = {table_name(table, i) for i, table in enumerate(tables or [])}
    for path, score in overrides.items():
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] in table_names:
            row_index, column = int(parts[1]), parts[2]
            members = groups.get(column, [])
            if row_index < len(members):
                flat[_join_path("", members[row_index])] = score
        else:
            flat[path] = score
    return flat


def count_blank_mismatches(actual: dict, expected: dict) -> tuple[int, int]:
    """Return (missing, unsupported): expected values the model left blank, and
    blank or unknown fields the model populated."""
    missing = unsupported = 0
    for key, expected_value in expected.items():
        if _is_ignored_field(_join_path("", key)):
            continue
        expected_blank = _is_blank(expected_value)
        actual_blank = _is_blank(actual.get(key, ""))
        if expected_blank and not actual_blank:
            unsupported += 1
        elif not expected_blank and actual_blank:
            missing += 1
    unsupported += sum(
        1 for key, value in actual.items()
        if key not in expected and not _is_blank(value)
    )
    return missing, unsupported


def _join_path(parent: str, child: Any) -> str:
    escaped = str(child).replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}" if parent else f"/{escaped}"


def _populated_ground_truth(value: Any, path: str = "") -> Any:
    """Return ground truth containing only fields expected to be populated."""
    if _is_ignored_field(path):
        return _EXCLUDED

    if isinstance(value, dict):
        populated = {}
        for key, child in value.items():
            filtered = _populated_ground_truth(child, _join_path(path, key))
            if filtered is not _EXCLUDED:
                populated[key] = filtered
        return populated if populated else _EXCLUDED

    if isinstance(value, list):
        populated = []
        for index, child in enumerate(value):
            filtered = _populated_ground_truth(child, _join_path(path, index))
            if filtered is not _EXCLUDED:
                populated.append(filtered)
        return populated if populated else _EXCLUDED

    if _is_empty_value(value) or _is_unchecked_checkbox(path, value):
        return _EXCLUDED
    return value


def find_structure_differences(
    actual: Any,
    expected: Any,
    path: str = "",
) -> tuple[list[str], list[str], list[str]]:
    """Return missing paths, extra paths, and container type mismatches."""
    missing: list[str] = []
    extra: list[str] = []
    wrong_types: list[str] = []

    if _is_ignored_field(path):
        return missing, extra, wrong_types

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            wrong_types.append(path or "/")
            return missing, extra, wrong_types

        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in expected_keys - actual_keys:
            child_path = _join_path(path, key)
            if _is_ignored_field(child_path):
                continue
            if _is_unchecked_checkbox(child_path, expected[key]):
                continue
            missing.append(child_path)
        extra.extend(_join_path(path, key) for key in actual_keys - expected_keys)

        for key in expected_keys & actual_keys:
            child = find_structure_differences(
                actual[key], expected[key], _join_path(path, key)
            )
            missing.extend(child[0])
            extra.extend(child[1])
            wrong_types.extend(child[2])

    elif isinstance(expected, list):
        if not isinstance(actual, list):
            wrong_types.append(path or "/")
            return missing, extra, wrong_types

        shared_length = min(len(actual), len(expected))
        for index in range(shared_length):
            child = find_structure_differences(
                actual[index], expected[index], _join_path(path, index)
            )
            missing.extend(child[0])
            extra.extend(child[1])
            wrong_types.extend(child[2])
        missing.extend(
            _join_path(path, index)
            for index in range(shared_length, len(expected))
        )
        extra.extend(
            _join_path(path, index)
            for index in range(shared_length, len(actual))
        )

    elif isinstance(actual, (dict, list)):
        wrong_types.append(path or "/")

    return sorted(missing), sorted(extra), sorted(wrong_types)


def _count_leaves(value: Any, path: str = "") -> int:
    if _is_ignored_field(path):
        return 0
    if isinstance(value, dict):
        return sum(
            _count_leaves(child, _join_path(path, key))
            for key, child in value.items()
        )
    if isinstance(value, list):
        return sum(
            _count_leaves(child, _join_path(path, index))
            for index, child in enumerate(value)
        )
    return 1


def _count_present_leaves(actual: Any, expected: Any, path: str = "") -> int:
    if _is_ignored_field(path):
        return 0
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return 0
        present = 0
        for key, child in expected.items():
            child_path = _join_path(path, key)
            if _is_ignored_field(child_path):
                continue
            if key in actual:
                present += _count_present_leaves(
                    actual[key], child, child_path
                )
            elif _is_unchecked_checkbox(child_path, child):
                # An omitted unchecked checkbox is equivalent to PDF value Off.
                present += _count_leaves(child, child_path)
        return present
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return 0
        return sum(
            _count_present_leaves(
                actual[index], child, _join_path(path, index)
            )
            for index, child in enumerate(expected)
            if index < len(actual)
        )
    return 0 if isinstance(actual, (dict, list)) else 1


def _field_name_from_path(path: str) -> str:
    """Return the final, unescaped field name from a JSON Pointer path."""
    name = path.rsplit("/", 1)[-1] if path != "/" else "/"
    return name.replace("~1", "/").replace("~0", "~")


def find_inaccurate_fields(
    actual: Any,
    expected: Any,
    overrides: dict[str, float] | None = None,
    path: str = "",
) -> list[dict[str, Any]]:
    """Return fields whose final score remains below 1.0."""
    if _is_ignored_field(path):
        return []

    if isinstance(expected, dict) and isinstance(actual, dict) and expected:
        inaccurate: list[dict[str, Any]] = []
        for key, child_expected in expected.items():
            child_path = _join_path(path, key)
            child_actual = actual[key] if key in actual else None
            inaccurate.extend(
                find_inaccurate_fields(
                    child_actual,
                    child_expected,
                    overrides,
                    child_path,
                )
            )
        return inaccurate

    score = calculate_accuracy(actual, expected, overrides, path)
    if score >= 1.0:
        return []

    final_path = path or "/"
    return [{
        "field_name": _field_name_from_path(final_path),
        "path": final_path,
        "score": score,
    }]


def run_compare(
    json_template: Any | None = None,
    *,
    ground_truth_path: str | Path,
    test_path: str | Path,
    narrative_path: str | Path,
    use_llm_judge: bool = True,
    tables: list | None = None,
    groups: dict | None = None,
) -> dict[str, Any]:
    """Compare an extracted JSON file using the supplied template shape.

    ``tables`` and ``groups`` come from ``form_filler.template.create_template``; when
    given, table rows are matched by content rather than by row number."""
    with Path(ground_truth_path).open("r", encoding="utf-8") as file:
        ground_truth_content = json.load(file)

    with Path(test_path).open("r", encoding="utf-8") as file:
        extracted = json.load(file)

    shaped_ground_truth = (
        ground_truth_content
        if json_template is None
        else build_ground_truth_shape(json_template, ground_truth_content)
    )
    # Headline scores use folded tables; diagnostics below stay flat for the review PDFs.
    scored_ground_truth = fold_tables(shaped_ground_truth, tables, groups)
    scored_extracted = fold_tables(extracted, tables, groups)
    raw_accuracy = calculate_accuracy(scored_extracted, scored_ground_truth)
    populated_ground_truth = _populated_ground_truth(scored_ground_truth)
    populated_raw_accuracy = (
        1.0
        if populated_ground_truth is _EXCLUDED
        else calculate_accuracy(
            scored_extracted, populated_ground_truth, penalize_extras=False
        )
    )
    judged = None
    accuracy = raw_accuracy
    populated_accuracy = populated_raw_accuracy
    if use_llm_judge:
        with Path(narrative_path).open("r", encoding="utf-8") as file:
            narrative = file.read()
        judged = calculate_accuracy_with_judge(
            scored_extracted,
            scored_ground_truth,
            narrative,
        )
        accuracy = judged["adjusted_score"]
        if populated_ground_truth is not _EXCLUDED:
            populated_accuracy = calculate_accuracy(
                scored_extracted,
                populated_ground_truth,
                judged["judge"]["overrides"],
                penalize_extras=False,
            )
    missing, extra, wrong_types = find_structure_differences(
        extracted, shaped_ground_truth
    )
    missing_count, unsupported_count = count_blank_mismatches(
        extracted, shaped_ground_truth
    )

    required_leaves = _count_leaves(shaped_ground_truth)
    present_leaves = _count_present_leaves(extracted, shaped_ground_truth)
    completeness = present_leaves / required_leaves if required_leaves else 1.0

    print(f"Raw benchmark accuracy (total): {raw_accuracy:.2%}")
    print(f"Missing values: {missing_count}   Unsupported values: {unsupported_count}")
    print(
        "Raw benchmark accuracy (populated only): "
        f"{populated_raw_accuracy:.2%}"
    )
    if judged is not None and judged["judge"]["applied"]:
        print(f"LLM-judged accuracy (total): {accuracy:.2%}")
        print(f"LLM-judged accuracy (populated only): {populated_accuracy:.2%}")
        # print(f"Judge decisions applied: {len(judged['judge']['overrides'])}")
    elif judged is not None and judged["judge"]["error"]:
        print(f"LLM judge unavailable: {judged['judge']['error']}")
        print(f"LLM-judged accuracy (total): {accuracy:.2%} (raw fallback)")
        print(
            "LLM-judged accuracy (populated only): "
            f"{populated_accuracy:.2%} (raw fallback)"
        )
    elif judged is not None:
        print(f"LLM-judged accuracy (total): {accuracy:.2%} (no candidates)")
        print(
            "LLM-judged accuracy (populated only): "
            f"{populated_accuracy:.2%} (no candidates)"
        )

    overrides = None
    if judged is not None:
        overrides = flatten_overrides(judged["judge"]["overrides"], tables, groups)
    inaccurate_fields = find_inaccurate_fields(
        extracted,
        shaped_ground_truth,
        overrides,
    )
    # Per-field mismatch output is intentionally disabled to keep benchmark
    # results concise. The details remain available in ``inaccurate_fields``
    # in the returned result.
    # result_label = (
    #     "Inaccurate field after LLM judge"
    #     if judged and judged["judge"]["applied"]
    #     else "Inaccurate field"
    # )
    # for item in inaccurate_fields:
    #     print(
    #         f"{result_label}: {item['field_name']} "
    #         f"({item['score']:.2%})"
    #     )

    # print(f"Leaf values present: {present_leaves}/{required_leaves}")
    # print(f"Completeness: {completeness:.2%}")

    # for item in missing:
    #     print(f"Missing: {item}")
    # for item in extra:
    #     print(f"Unexpected extra field: {item}")
    # for item in wrong_types:
    #     print(f"Wrong structure/type: {item}")

    return {
        "accuracy": accuracy,
        "raw_accuracy": raw_accuracy,
        "populated_accuracy": populated_accuracy,
        "populated_raw_accuracy": populated_raw_accuracy,
        "judge": None if judged is None else judged["judge"],
        "inaccurate_fields": inaccurate_fields,
        "completeness": completeness,
        "missing_count": missing_count,
        "unsupported_count": unsupported_count,
        "missing": missing,
        "extra": extra,
        "wrong_types": wrong_types,
        "ground_truth": shaped_ground_truth,
    }
