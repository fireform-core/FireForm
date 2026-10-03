"""wrong_fields.txt: every field the scorer marked wrong, expected vs got,
with the score before and after the LLM judge.

Tables are walked the way the scorer sees them: folded into rows, each
expected row paired with its best-matching output row (accuracy.match_rows),
so a row the model wrote in a different order is not reported as wrong.
"""

import textwrap

from accuracy import _is_blank, _is_empty_value, _is_ignored_field, calculate_accuracy, match_rows
from compare import _join_path, fold_tables

WIDTH = 100


def doc_entries(values, ground_truth, tables, groups, judge):
    """[{field, expected, got, raw, verdict, reason, final}] for one document."""
    decisions = {d["path"]: d for d in (judge or {}).get("decisions", [])}
    expected = fold_tables(ground_truth, tables, groups)
    actual = fold_tables(values, tables, groups)

    entries = []
    for key, expected_value in expected.items():
        path = _join_path("", key)
        if _is_ignored_field(path):
            continue
        if isinstance(expected_value, list):
            entries += table_entries(key, path, actual.get(key, []), expected_value, decisions)
            continue

        got = actual.get(key)
        if key in actual:
            raw = calculate_accuracy(got, expected_value, None, path)
        else:
            raw = 1.0 if _is_blank(expected_value) else 0.0
        if raw < 1.0:
            entries.append(entry(key, expected_value, got, raw, decisions.get(path)))

    # Populated keys the form does not have (the scorer counts these as wrong)
    for key, got in actual.items():
        if key not in expected and not _is_blank(got):
            entries.append(entry(key, None, got, 0.0, None))
    return entries


def table_entries(key, path, actual_rows, expected_rows, decisions):
    entries = []
    expected_rows = [row for row in expected_rows if not _is_blank(row)]
    pairs, unmatched = match_rows(actual_rows, expected_rows, None, path)

    for index, (expected_row, matched_row, _) in enumerate(pairs):
        if matched_row is None:
            entries.append(entry(f"{key} row {index + 1}", row_text(expected_row), None, 0.0, None))
            continue
        for column, expected_value in expected_row.items():
            cell_path = _join_path(_join_path(path, index), column)
            got = matched_row.get(column)
            raw = calculate_accuracy(got if got is not None else "", expected_value, None, cell_path)
            if raw < 1.0:
                label = f"{key} row {index + 1} / {column}"
                entries.append(entry(label, expected_value, got, raw, decisions.get(cell_path)))

    for row in unmatched:
        entries.append(entry(f"{key} extra row", None, row_text(row), 0.0, None))
    return entries


def entry(field, expected, got, raw, decision):
    if decision is None:
        verdict, reason, final = None, "", raw
    else:
        verdict = "PASS" if decision["correct"] else "FAIL"
        reason = decision["reason"]
        final = 1.0 if decision["correct"] else 0.0
    return {"field": field, "expected": expected, "got": got, "raw": raw,
            "verdict": verdict, "reason": reason, "final": final}


def row_text(row):
    return " | ".join(f"{k}: {v}" for k, v in row.items() if not _is_blank(v))


# ------------------------------------------------------------------ writing

def show(value):
    if _is_empty_value(value):
        return "(blank)"
    return str(value)


def wrapped(label, value):
    lines = textwrap.wrap(show(value), WIDTH - 17) or [""]
    out = [f"      {label:<9}: {lines[0]}"]
    out += [" " * 17 + line for line in lines[1:]]
    return out


def format_entry(e):
    lines = [f"  {e['field']}"]
    lines += wrapped("expected", e["expected"])
    lines += wrapped("got", e["got"])
    if e["verdict"] is None:
        judge = "not judged"
    else:
        judge = f"judge {e['verdict']}: {e['reason']}"
    lines.append(f"      raw {e['raw']:.2f}  ->  {judge}  ->  final {e['final']:.2f}")
    return lines


def format_doc(doc, result, entries):
    still_wrong = [e for e in entries if e["final"] < 1.0]
    accepted = [e for e in entries if e["final"] >= 1.0]
    lines = [
        "=" * WIDTH,
        f"{doc}    raw {result['raw_accuracy']:.1%} -> judged {result['accuracy']:.1%}    "
        f"{len(still_wrong)} wrong, {len(accepted)} accepted by judge",
        "=" * WIDTH,
    ]
    if still_wrong:
        lines.append("WRONG AFTER JUDGE")
        for e in still_wrong:
            lines += format_entry(e)
    if accepted:
        lines.append("")
        lines.append("WRONG BEFORE JUDGE, ACCEPTED BY JUDGE")
        for e in accepted:
            lines += format_entry(e)
    if not entries:
        lines.append("  (no wrong fields)")
    lines.append("")
    return lines


def write(path, model, docs, skipped):
    """docs: [(doc, result, entries)] in run order; skipped: [(doc, reason)]."""
    lines = [
        f"Wrong fields - model {model}",
        "raw = scorer before the LLM judge, final = after it (judge PASS -> 1.00, FAIL -> 0.00).",
        "Table cells are compared against the output row the scorer matched, not by position.",
        "",
    ]
    for doc, reason in skipped:
        lines.append(f"SKIPPED {doc}: {reason}")
    if skipped:
        lines.append("")
    for doc, result, entries in docs:
        lines += format_doc(doc, result, entries)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
