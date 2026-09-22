from typing import Any
from benchmark.evaluators.JSONValidator import JSONValidator
from benchmark.evaluators.accuracy_calculator import AccuracyCalculator


def do_they_have_same_shape(extracted: Any, ground_truth: Any, verbose: bool = False) -> bool:
    """
    Validates if extracted and ground_truth conform to the same JSON structure.
    """
    return JSONValidator.json_shape_validator_with_log(extracted, ground_truth, verbose=verbose)


def calculate_accuracy(extracted: Any, ground_truth: Any, verbose: bool = True, use_llm_judge: bool = True) -> float:
    """
    Computes a score from 0.0 to 1.0 representing accuracy (correct values / all values).
    Utilizes deterministic matching, date normalization, fuzzy matching, and batched LLM judge fallback.
    """
    return AccuracyCalculator.calculate_accuracy(
        extracted,
        ground_truth,
        verbose=verbose,
        use_llm_judge=use_llm_judge,
    )

#     with open("extracted.json", "w") as f:
#         json.dump(extracted, f)
#     with open("ground_truth.json", "w") as f:
#         json.dump(ground_truth, f)

#     if extracted is None and ground_truth is None:
#         return 1.0
#     if extracted is None or ground_truth is None:
#         return 0.0

#     # 1. Dictionary Comparison: Average score across all ground_truth keys
#     if isinstance(ground_truth, dict):
#         if not isinstance(extracted, dict):
#             print(f"❌ Type mismatch: expected dict, got {type(extracted).__name__}")
#             return 0.0
#         if not ground_truth and not extracted:
#             return 1.0
#         if not ground_truth:
#             return 1.0

#         total_score = 0.0
#         for k, gt_val in ground_truth.items():
#             if k in extracted:
#                 total_score += calculate_accuracy(extracted[k], gt_val)
#             else:
#                 print(f"❌ Missing key '{k}': expected {gt_val}")
#                 total_score += 0.0
#         return total_score / len(ground_truth)

#     # 2. List Comparison: Best-match greedy alignment averaged over list length
#     if isinstance(ground_truth, list):
#         if not isinstance(extracted, list):
#             print(f"❌ Type mismatch: expected list, got {type(extracted).__name__}")
#             return 0.0
#         if not ground_truth and not extracted:
#             return 1.0
#         if not ground_truth:
#             return 0.0

#         temp_extracted = list(extracted)
#         matched_scores = []
#         for gt_item in ground_truth:
#             best_match = 0.0
#             best_idx = -1
#             for idx, ext_item in enumerate(temp_extracted):
#                 score = calculate_accuracy(ext_item, gt_item)
#                 if score > best_match:
#                     best_match = score
#                     best_idx = idx
#             matched_scores.append(best_match)
#             if best_idx != -1:
#                 temp_extracted.pop(best_idx)

#         # Penalize extra or missing items by dividing by max length
#         divisor = max(len(ground_truth), len(extracted))
#         return sum(matched_scores) / divisor if divisor > 0 else 1.0

#     # 3. Boolean Comparison
#     if isinstance(ground_truth, bool):
#         if isinstance(extracted, str):
#             extracted = extracted.strip().lower() in ("true", "1", "yes")
#         is_match = (extracted is ground_truth)
#         if is_match:
#             print(f"✅ {extracted} == {ground_truth}")
#             return 1.0
#         else:
#             print(f"❌ {extracted} != {ground_truth}")
#             return 0.0

#     # 4. Numeric Comparison
#     if isinstance(ground_truth, (int, float)):
#         try:
#             is_match = (float(extracted) == float(ground_truth))
#             if is_match:
#                 print(f"✅ {extracted} == {ground_truth}")
#                 return 1.0
#             else:
#                 print(f"❌ {extracted} != {ground_truth}")
#                 return 0.0
#         except (ValueError, TypeError):
#             print(f"❌ {extracted} != {ground_truth} (cannot parse as number)")
#             return 0.0

#     # 5. String Comparison
#     if isinstance(ground_truth, str):
#         if not isinstance(extracted, str):
#             extracted = str(extracted) if extracted is not None else ""
#         if extracted.strip().lower() == ground_truth.strip().lower():
#             print(f"✅ {extracted} == {ground_truth}")
#             return 1.0
#         sim = fuzzy_string_similarity(extracted, ground_truth)
#         if sim >= 0.5:
#             print(f"✅ {extracted} ~= {ground_truth} (sim: {sim:.2f})")
#             return sim
#         else:
#             print(f"❌ {extracted} != {ground_truth}")
#             return 0.0

#     is_match = (extracted == ground_truth)
#     if is_match:
#         print(f"✅ {extracted} == {ground_truth}")
#         return 1.0
#     else:
#         print(f"❌ {extracted} != {ground_truth}")
#         return 0.0


# def fuzzy_string_similarity(s1: str, s2: str) -> float:
#     """
#     Computes a simple token-based overlap similarity score between 0.0 and 1.0.
#     """
#     s1_clean = set(re.findall(r'\w+', s1.lower()))
#     s2_clean = set(re.findall(r'\w+', s2.lower()))
    
#     if not s1_clean or not s2_clean:
#         return 1.0 if s1_clean == s2_clean else 0.0

#     intersection = s1_clean.intersection(s2_clean)
#     union = s1_clean.union(s2_clean)
    
#     # Jaccard index
#     return len(intersection) / len(union)
