import re
from typing import Any


def calculate_accuracy(extracted: Any, ground_truth: Any) -> float:
    """
    Computes a score from 0.0 to 1.0 representing accuracy.
    Handles nested dicts, lists, booleans, and string fuzzy matching.
    """
    # IncidentContract responses intentionally include unavailable fields as
    # JSON null. Two nulls are an exact match; previously they fell through to
    # the default return value and incorrectly scored as zero.
    if ground_truth is None:
        return 1.0 if extracted is None else 0.0

    if type(extracted) is not type(ground_truth):
        # Allow string representations of booleans/numbers
        if isinstance(ground_truth, bool) and isinstance(extracted, str):
            extracted = extracted.lower() in ("true", "1", "yes")
        elif (
            isinstance(ground_truth, (int, float))
            and not isinstance(ground_truth, bool)
            and isinstance(extracted, (int, float))
            and not isinstance(extracted, bool)
        ):
            return 1.0 if extracted == ground_truth else 0.0
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
        return fuzzy_string_similarity(extracted, ground_truth)

    if isinstance(ground_truth, dict):
        if not ground_truth:
            return 1.0
        total_score = 0.0
        keys = ground_truth.keys()
        for k in keys:
            if k in extracted:
                total_score += calculate_accuracy(extracted[k], ground_truth[k])
        return total_score / len(keys)

    if isinstance(ground_truth, list):
        if not ground_truth:
            return 1.0 if not extracted else 0.0
        # Compute match score for list items
        matched_scores = []
        temp_extracted = list(extracted)
        for gt_item in ground_truth:
            best_match = 0.0
            best_idx = -1
            for idx, ext_item in enumerate(temp_extracted):
                score = calculate_accuracy(ext_item, gt_item)
                if score > best_match:
                    best_match = score
                    best_idx = idx
            matched_scores.append(best_match)
            if best_idx != -1:
                temp_extracted.pop(best_idx)
        # Missing and surplus list items are both errors. Dividing only by the
        # ground-truth length gave a perfect score to [correct, hallucinated].
        return sum(matched_scores) / max(len(ground_truth), len(extracted))

    return 0.0


def fuzzy_string_similarity(s1: str, s2: str) -> float:
    """
    Computes a simple token-based overlap similarity score between 0.0 and 1.0.
    """
    s1_clean = set(re.findall(r"\w+", s1.lower()))
    s2_clean = set(re.findall(r"\w+", s2.lower()))

    if not s1_clean or not s2_clean:
        return 1.0 if s1_clean == s2_clean else 0.0

    intersection = s1_clean.intersection(s2_clean)
    union = s1_clean.union(s2_clean)

    # Jaccard index
    return len(intersection) / len(union)
