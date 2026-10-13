import re

# Expected values this short must match exactly; longer text is scored by token overlap.
# Formatting and naming differences in short fields are left to the LLM judge.
SHORT_FIELD_MAX_TOKENS = 6


def normalize_tokens(text: str) -> list[str]:
    """Ordered lowercase word tokens."""
    return re.findall(r"\w+", text.lower())


def _is_empty_value(value: any) -> bool:
    """Return whether a value is empty for benchmark purposes."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return not value or all(_is_empty_value(child) for child in value.values())
    if isinstance(value, list):
        return not value or all(_is_empty_value(child) for child in value)
    return False


def _is_unchecked_checkbox(path: str, ground_truth: any) -> bool:
    """Return whether this value uses the PDF unchecked-checkbox convention.

    Ground-truth files use ``Off`` exclusively for unchecked PDF fields. Some
    checkbox names (for example ``ICS 203`` or ``Map/Chart``) do not contain
    the word "checkbox", so the value is the reliable signal here.
    """
    return isinstance(ground_truth, str) and ground_truth.strip().lower() == "off"


def _is_blank(value: any) -> bool:
    """Blank for scoring: empty text, an unchecked box, or a container holding only those."""
    if isinstance(value, dict):
        return all(_is_blank(child) for child in value.values())
    if isinstance(value, list):
        return all(_is_blank(child) for child in value)
    return _is_empty_value(value) or _is_unchecked_checkbox("", value)


def _is_ignored_field(path: str) -> bool:
    """Return whether a benchmark field is temporarily excluded from scoring."""
    if not path:
        return False
    field_name = path.rsplit("/", 1)[-1]
    field_name = field_name.replace("~1", "/").replace("~0", "~")
    return "signature" in field_name.lower()


def calculate_accuracy(
    extracted: any,
    ground_truth: any,
    _overrides: dict[str, float] | None = None,
    _path: str = "",
    penalize_extras: bool = True,
) -> float:
    """
    Computes a score from 0.0 to 1.0 representing accuracy.
    Handles nested dicts, lists, booleans, and string fuzzy matching.

    ``penalize_extras`` counts populated keys and table rows that the ground
    truth does not have. Pass False when scoring against a populated-only
    subset of the ground truth, where absent keys are not evidence of error.
    """
    if _is_ignored_field(_path):
        return 1.0

    override_path = _path or "/"
    if _overrides and override_path in _overrides:
        return _overrides[override_path]

    # Blank ground-truth fields are valid negatives: an omitted or blank
    # extracted value passes, while a populated extracted value fails.
    if _is_empty_value(ground_truth):
        return 1.0 if _is_empty_value(extracted) else 0.0

    # PDF checkbox APIs commonly omit unchecked fields or expose them as an
    # empty value. Treat that representation as the PDF value "Off".
    if _is_unchecked_checkbox(_path, ground_truth) and _is_empty_value(extracted):
        return 1.0

    if type(extracted) is not type(ground_truth):
        # Allow string representations of booleans/numbers
        if isinstance(ground_truth, bool) and isinstance(extracted, str):
            extracted = extracted.lower() in ("true", "1", "yes")
        elif isinstance(ground_truth, (int, float)) and isinstance(extracted, str):
            try:
                extracted = float(extracted) if isinstance(ground_truth, float) else int(extracted)
            except ValueError:
                return 0.0
        else:
            return 0.0

    if isinstance(ground_truth, bool):
        return 1.0 if extracted == ground_truth else 0.0

    if isinstance(ground_truth, (int, float)):
        return 1.0 if extracted == ground_truth else 0.0

    if isinstance(ground_truth, str):
        return string_similarity(extracted, ground_truth)

    if isinstance(ground_truth, dict):
        total_score = 0.0
        scored_fields = 0
        for k, expected_value in ground_truth.items():
            escaped = str(k).replace("~", "~0").replace("/", "~1")
            child_path = f"{_path}/{escaped}" if _path else f"/{escaped}"
            if _is_ignored_field(child_path):
                continue

            scored_fields += 1
            if k in extracted:
                total_score += calculate_accuracy(
                    extracted[k], expected_value, _overrides, child_path, penalize_extras
                )
            elif _is_empty_value(expected_value):
                # Missing output for a blank expected field is a pass.
                total_score += 1.0
            else:
                if _is_unchecked_checkbox(child_path, expected_value):
                    total_score += 1.0
        # Populated values for keys the form does not have are unsupported.
        if penalize_extras:
            scored_fields += sum(
                1 for k, value in extracted.items()
                if k not in ground_truth and not _is_blank(value)
            )
        return total_score / scored_fields if scored_fields else 1.0

    if isinstance(ground_truth, list):
        # Rows are matched by content, not position, so reordered rows still pass.
        expected_rows = [row for row in ground_truth if not _is_blank(row)]
        if not expected_rows:
            return 1.0 if _is_blank(extracted) else 0.0
        pairs, unmatched = match_rows(
            extracted, expected_rows, _overrides, _path, penalize_extras
        )
        # Rows left over after matching are unsupported and count against the score.
        unsupported_rows = len(unmatched) if penalize_extras else 0
        return sum(score for _, _, score in pairs) / (len(pairs) + unsupported_rows)

    return 0.0


def match_rows(
    extracted_rows: list,
    expected_rows: list,
    overrides: dict[str, float] | None = None,
    path: str = "",
    penalize_extras: bool = True,
) -> tuple[list[tuple[any, any, float]], list]:
    """Pair each expected row with its best-scoring unused extracted row.

    Returns ``(pairs, unmatched)``: one ``(expected_row, matched_row, score)``
    per expected row, with ``matched_row`` None when nothing matched, and the
    extracted rows left over. Rows are scored under ``path/<expected index>``
    so judge overrides for table cells line up with the scorer.
    """
    remaining = [row for row in extracted_rows if not _is_blank(row)]
    pairs = []
    for index, expected_row in enumerate(expected_rows):
        if remaining:
            scores = [
                calculate_accuracy(row, expected_row, overrides, f"{path}/{index}", penalize_extras)
                for row in remaining
            ]
            best = max(scores, default=0.0)
            matched = remaining.pop(scores.index(best))
        else:
            best = 0.0
            matched = None
        pairs.append((expected_row, matched, best))
    return pairs, remaining


def calculate_accuracy_with_judge(
    extracted: any,
    ground_truth: any,
    narrative: str,
) -> dict:
    """Return raw and self-judged scores while preserving judge audit details."""
    from llm_judge import judge_low_scoring_fields

    raw_score = calculate_accuracy(extracted, ground_truth)
    judgment = judge_low_scoring_fields(
        extracted,
        ground_truth,
        narrative,
        calculate_accuracy,
    )
    adjusted_score = calculate_accuracy(
        extracted,
        ground_truth,
        judgment["overrides"],
    )
    return {
        "raw_score": raw_score,
        "adjusted_score": adjusted_score,
        "judge": judgment,
    }


def string_similarity(extracted: str, expected: str) -> float:
    """Short values must match exactly after normalization; long text keeps token overlap."""
    extracted_tokens = normalize_tokens(extracted)
    expected_tokens = normalize_tokens(expected)
    if extracted_tokens == expected_tokens:
        return 1.0
    if len(expected_tokens) <= SHORT_FIELD_MAX_TOKENS or not extracted_tokens:
        return 0.0
    overlap = set(extracted_tokens) & set(expected_tokens)
    return len(overlap) / len(set(extracted_tokens) | set(expected_tokens))


def calculate_accuracy_flat(extracted_flat: list[str], ground_truth_flat: list[dict]) -> float:
    """Compare flat extracted values against flat ground truth entry-by-entry.

    extracted_flat: list of string values in widget order (from approach_d).
    ground_truth_flat: list of {type, description, value} dicts in widget order.
    Only non-empty ground truth values contribute to the score.
    """
    if not ground_truth_flat:
        return 1.0

    scores = []
    for i, gt_entry in enumerate(ground_truth_flat):
        gt_val = str(gt_entry.get("value", ""))
        if not gt_val:
            continue
        ext_val = extracted_flat[i] if i < len(extracted_flat) else ""
        scores.append(string_similarity(str(ext_val), gt_val))

    return sum(scores) / len(scores) if scores else 0.0
