"""Create a color-coded review copy of a benchmark PDF."""

import re
from pathlib import Path

from pypdf import PdfWriter
from pypdf.annotations import Rectangle
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

from accuracy import _is_empty_value, calculate_accuracy
from app.services.form_filler.geometry import page_widgets


COLORS = {
    "missing": (1, 0.55, 0),
    "wrong": (1, 0, 0),
    "partial": (1, 0.85, 0),
}

# These rows are semantically unordered. Exact rows may move without being wrong.
UNORDERED_ROWS = {
    "ics_205a": (
        "Name AlphabetizedRow",
        "Incident Assigned PositionRow",
        "Methods of Contact phone pager cell etcRow",
    ),
}


def _value_at(data, path):
    value = data
    for part in path.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _ignore_reordered_rows(case_name, failures, actual, expected):
    stems = next(
        (columns for form, columns in UNORDERED_ROWS.items() if case_name.startswith(form + "_")),
        None,
    )
    if not stems:
        return

    row_numbers = {
        int(match.group(1))
        for key in set(actual) | set(expected)
        if any(key.startswith(stem) for stem in stems)
        if (match := re.search(r"Row(\d+)$", key))
    }
    expected_rows = {
        row: tuple(expected.get(f"{stem}{row}", "") for stem in stems)
        for row in row_numbers
        if any(expected.get(f"{stem}{row}", "") for stem in stems)
    }
    unused = set(expected_rows)
    for row in row_numbers:
        values = tuple(actual.get(f"{stem}{row}", "") for stem in stems)
        matches = {
            candidate: sum(
                calculate_accuracy(value, expected_rows[candidate][index])
                for index, value in enumerate(values)
            ) / len(stems)
            for candidate in unused
        }
        if any(values) and matches:
            matched_row = max(matches, key=matches.get)
        else:
            continue
        if matches[matched_row] >= 0.8:
            for stem in stems:
                failures.pop(f"{stem}{row}", None)
                failures.pop(f"{stem}{matched_row}", None)
            unused.remove(matched_row)


def create_review_pdf(case_name, input_pdf, output_pdf, actual, comparison):
    """Highlight missing, wrong, and partially matching fields."""
    expected = comparison["ground_truth"]
    failures = {
        item["field_name"]: item
        for item in comparison["inaccurate_fields"]
        if not _is_empty_value(_value_at(expected, item["path"]))
    }
    _ignore_reordered_rows(case_name, failures, actual, expected)

    document = PdfWriter(clone_from=input_pdf)
    marked = set()
    for page_number, page in enumerate(document.pages):
        for widget in page_widgets(page):
            failure = failures.get(widget.field_name)
            if not failure:
                continue

            expected_value = _value_at(expected, failure["path"])
            actual_value = _value_at(actual, failure["path"])
            if _is_empty_value(actual_value):
                category = "missing"
            elif failure["score"] <= 0:
                category = "wrong"
            else:
                category = "partial"

            color = ArrayObject(FloatObject(c) for c in COLORS[category])
            annotation = Rectangle(rect=widget.rect)
            annotation[NameObject("/C")] = color
            annotation[NameObject("/IC")] = color
            annotation[NameObject("/CA")] = FloatObject(0.22)
            annotation[NameObject("/BS")] = DictionaryObject(
                {NameObject("/W"): FloatObject(1.5)}
            )
            annotation[NameObject("/T")] = TextStringObject(category.title())
            annotation[NameObject("/Contents")] = TextStringObject(
                f"Expected: {expected_value!s}\n"
                f"Actual: {actual_value if actual_value is not None else '<missing>'}\n"
                f"Score: {failure['score']:.0%}"
            )
            document.add_annotation(page_number, annotation)
            marked.add(widget.field_name)

    output_path = Path(output_pdf)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    document.write(output_path)
    document.close()
    return len(marked), sorted(set(failures) - marked)
