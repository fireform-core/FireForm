import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
import requests


DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%H:%M",
    "%H:%M:%S",
]


def try_parse_datetime(val: str) -> Optional[datetime]:
    if not isinstance(val, str):
        return None
    val_clean = val.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val_clean, fmt)
        except ValueError:
            pass
    return None


class AccuracyCalculator:
    def __init__(self):
        pass

    @staticmethod
    def fuzzy_string_similarity(s1: str, s2: str) -> float:
        """
        Computes a similarity score between two strings using
        token Jaccard similarity and character-level SequenceMatcher.
        """
        if not isinstance(s1, str):
            s1 = str(s1) if s1 is not None else ""
        if not isinstance(s2, str):
            s2 = str(s2) if s2 is not None else ""

        str1_norm = s1.strip().lower()
        str2_norm = s2.strip().lower()

        if str1_norm == str2_norm:
            return 1.0

        # Character sequence similarity
        seq_sim = SequenceMatcher(None, str1_norm, str2_norm).ratio()

        # Token overlap similarity (Jaccard)
        tokens1 = set(re.findall(r"\w+", str1_norm))
        tokens2 = set(re.findall(r"\w+", str2_norm))

        if not tokens1 or not tokens2:
            token_sim = 1.0 if tokens1 == tokens2 else 0.0
        else:
            token_sim = len(tokens1 & tokens2) / len(tokens1 | tokens2)

        return max(seq_sim, token_sim)

    @staticmethod
    def _evaluate_node(
        extracted: Any,
        ground_truth: Any,
        path: str,
        pending_llm_candidates: List[Dict[str, Any]],
        leaf_scores: List[float],
        verbose: bool = True,
        fuzzy_threshold: float = 0.65,
    ) -> float:
        """
        Internal recursive evaluator that scores fields and registers string mismatches
        into pending_llm_candidates for batched LLM evaluation.
        """
        if extracted is None and ground_truth is None:
            if verbose:
                print(f"  ✅ [{path}] None == None")
            leaf_scores.append(1.0)
            return 1.0
        if extracted is None or ground_truth is None:
            if verbose:
                print(f"  ❌ [{path}] None mismatch: extracted={extracted}, expected={ground_truth}")
            leaf_scores.append(0.0)
            return 0.0

        # 1. Dictionary Comparison
        if isinstance(ground_truth, dict):
            if not isinstance(extracted, dict):
                if verbose:
                    print(f"  ❌ [{path}] Type mismatch: expected dict, got {type(extracted).__name__}")
                leaf_scores.append(0.0)
                return 0.0

            if not ground_truth:
                return 1.0

            sub_scores = []
            for key, gt_val in ground_truth.items():
                sub_path = key if path == "root" else f"{path}.{key}"
                if key in extracted:
                    s = AccuracyCalculator._evaluate_node(
                        extracted[key], gt_val, sub_path, pending_llm_candidates, leaf_scores, verbose, fuzzy_threshold
                    )
                    sub_scores.append(s)
                else:
                    if verbose:
                        print(f"  ❌ [{sub_path}] Missing key in extracted: expected {gt_val}")
                    leaf_scores.append(0.0)
                    sub_scores.append(0.0)

            return sum(sub_scores) / len(ground_truth) if ground_truth else 1.0

        # 2. List Comparison
        if isinstance(ground_truth, list):
            if not isinstance(extracted, list):
                if verbose:
                    print(f"  ❌ [{path}] Type mismatch: expected list, got {type(extracted).__name__}")
                leaf_scores.append(0.0)
                return 0.0

            if len(ground_truth) == 0 and len(extracted) == 0:
                if verbose:
                    print(f"  ✅ [{path}] Both lists are empty")
                leaf_scores.append(1.0)
                return 1.0

            if len(ground_truth) == 0 or len(extracted) == 0:
                if verbose:
                    print(f"  ❌ [{path}] Empty list mismatch: extracted has {len(extracted)} items, expected {len(ground_truth)}")
                leaf_scores.append(0.0)
                return 0.0

            remaining_extracted = list(enumerate(extracted))
            matched_scores: List[float] = []

            for gt_idx, gt_item in enumerate(ground_truth):
                best_score = -1.0
                best_ext_pos = -1
                best_orig_idx = -1

                for pos, (ext_idx, ext_item) in enumerate(remaining_extracted):
                    dummy_candidates: List[Dict[str, Any]] = []
                    dummy_leafs: List[float] = []
                    score = AccuracyCalculator._evaluate_node(
                        ext_item, gt_item, f"{path}[{ext_idx}]", dummy_candidates, dummy_leafs, verbose=False, fuzzy_threshold=fuzzy_threshold
                    )
                    if score > best_score:
                        best_score = score
                        best_ext_pos = pos
                        best_orig_idx = ext_idx

                if best_ext_pos != -1:
                    ext_item = remaining_extracted.pop(best_ext_pos)[1]
                    if verbose and isinstance(gt_item, (dict, list)):
                        print(f"\n  🔍 [{path}[{best_orig_idx}] vs ground_truth[{gt_idx}]] (Item score: {best_score:.2f})")
                    s = AccuracyCalculator._evaluate_node(
                        ext_item, gt_item, f"{path}[{best_orig_idx}]", pending_llm_candidates, leaf_scores, verbose, fuzzy_threshold
                    )
                    matched_scores.append(s)
                else:
                    matched_scores.append(0.0)
                    leaf_scores.append(0.0)
                    if verbose:
                        print(f"  ❌ [{path}] Missing item for ground_truth[{gt_idx}]: {gt_item}")

            divisor = max(len(ground_truth), len(extracted))
            final_list_score = sum(matched_scores) / divisor if divisor > 0 else 1.0

            if verbose and len(ground_truth) != len(extracted):
                print(f"  ⚠️  [{path}] Length difference: extracted {len(extracted)} items, expected {len(ground_truth)} items (List score: {final_list_score:.2%})")

            return final_list_score

        # 3. Boolean Comparison
        if isinstance(ground_truth, bool):
            is_match = (extracted is ground_truth)
            score = 1.0 if is_match else 0.0
            leaf_scores.append(score)
            if verbose:
                if is_match:
                    print(f"  ✅ [{path}] {extracted} == {ground_truth}")
                else:
                    print(f"  ❌ [{path}] {extracted} != {ground_truth}")
            return score

        # 4. Numeric Comparison
        if isinstance(ground_truth, (int, float)):
            try:
                is_match = (float(extracted) == float(ground_truth))
                score = 1.0 if is_match else 0.0
                leaf_scores.append(score)
                if verbose:
                    if is_match:
                        print(f"  ✅ [{path}] {extracted} == {ground_truth}")
                    else:
                        print(f"  ❌ [{path}] {extracted} != {ground_truth}")
                return score
            except (ValueError, TypeError):
                leaf_scores.append(0.0)
                if verbose:
                    print(f"  ❌ [{path}] Cannot compare as numbers: extracted={extracted}, expected={ground_truth}")
                return 0.0

        # 5. String Comparison
        if isinstance(ground_truth, str):
            extracted_str = str(extracted) if extracted is not None else ""

            if extracted_str.strip().lower() == ground_truth.strip().lower():
                leaf_scores.append(1.0)
                if verbose:
                    print(f"  ✅ [{path}] \"{extracted_str}\" == \"{ground_truth}\"")
                return 1.0

            # Direct Date/Time format match (e.g. ISO 8601 vs US format)
            dt_ext = try_parse_datetime(extracted_str)
            dt_gt = try_parse_datetime(ground_truth)
            if dt_ext and dt_gt and dt_ext == dt_gt:
                leaf_scores.append(1.0)
                if verbose:
                    print(f"  ✅ [{path}] (Date/Time Match)\n     Extracted: \"{extracted_str}\"\n     Expected:  \"{ground_truth}\"")
                return 1.0

            sim = AccuracyCalculator.fuzzy_string_similarity(extracted_str, ground_truth)
            if sim >= fuzzy_threshold:
                leaf_scores.append(sim)
                if verbose:
                    print(f"  ✅ [{path}] (Fuzzy {sim:.0%})\n     Extracted: \"{extracted_str}\"\n     Expected:  \"{ground_truth}\"")
                return sim
            else:
                # Register for LLM judge fallback
                leaf_idx = len(leaf_scores)
                leaf_scores.append(0.0)  # default initial score before judge

                candidate = {
                    "leaf_idx": leaf_idx,
                    "path": path,
                    "extracted": extracted_str,
                    "ground_truth": ground_truth,
                    "fuzzy_sim": sim,
                }
                pending_llm_candidates.append(candidate)

                if verbose:
                    print(f"  ❌ [{path}] (Mismatch {sim:.0%}) -> [Queued for LLM Judge]\n     Extracted: \"{extracted_str}\"\n     Expected:  \"{ground_truth}\"")
                return 0.0

        # Default fallback
        is_match = (extracted == ground_truth)
        score = 1.0 if is_match else 0.0
        leaf_scores.append(score)
        if verbose:
            if is_match:
                print(f"  ✅ [{path}] {extracted} == {ground_truth}")
            else:
                print(f"  ❌ [{path}] {extracted} != {ground_truth}")
        return score

    @staticmethod
    def _run_batch_llm_judge(
        candidates: List[Dict[str, Any]],
        model: str = "qwen2.5:1.5b",
        ollama_url: str = "http://localhost:11434/api/generate",
        verbose: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Sends a single batched prompt to the local LLM judge for all candidate string mismatches.
        Returns a dict mapping path -> {verdict: str, score: float, reason: str}.
        """
        if not candidates:
            return {}

        items_formatted = []
        for i, c in enumerate(candidates, start=1):
            items_formatted.append(
                f"Item {i}:\n"
                f"  - Field Path: {c['path']}\n"
                f"  - Ground Truth: \"{c['ground_truth']}\"\n"
                f"  - Extracted: \"{c['extracted']}\""
            )

        items_text = "\n\n".join(items_formatted)

        prompt = (
            "You are an intelligent, lenient evaluation judge assessing JSON data extraction accuracy for emergency incident management forms.\n"
            "Your task is to determine whether each 'Extracted' value is semantically, factually, or conceptually correct compared to 'Ground Truth'.\n\n"
            "CRITICAL JUDGMENT RULES:\n"
            "1. DATES & TIMES (EQUIVALENT): Any different date/time format representing the same date and time MUST be marked EQUIVALENT (e.g. '2026-05-18T17:00' vs '05/18/2026 17:00', ISO format vs US format).\n"
            "2. NUMBERS & CODES (EQUIVALENT): If the extracted text includes the target number or identifier within a longer phrase, it is EQUIVALENT (e.g. 'Page 1 of the comprehensive package' vs '1').\n"
            "3. NAMES & PEOPLE (EQUIVALENT): If the extracted name contains the target person's name plus their title, rank, or section, it is EQUIVALENT (e.g. 'Planning Section Chief Captain Rachel Brooks' vs 'Captain Rachel Brooks').\n"
            "4. POSITIONS & TITLES (EQUIVALENT or PARTIAL): If the extracted title refers to the same designated role or contains the core rank/section, mark EQUIVALENT or PARTIAL (e.g. 'Chief Captain' vs 'Planning Section Chief').\n"
            "5. DESCRIPTIONS & OBJECTIVES (EQUIVALENT or PARTIAL): If the extracted summary conveys the core intent or directive, mark EQUIVALENT.\n"
            "6. DO NOT BE OVERLY STRICT: Do not penalize phrasing differences, extra context, or standard format variations. Only mark INCORRECT (0.0) if the value is completely fabricated, factually contradictory, or refers to an entirely wrong entity.\n\n"
            "FEW-SHOT EXAMPLES:\n"
            "- Ground Truth: \"05/18/2026 17:00\" | Extracted: \"2026-05-18T17:00\" -> EQUIVALENT (Score 1.0) | Reason: Same timestamp in ISO 8601 format.\n"
            "- Ground Truth: \"1\" | Extracted: \"Page 1 of the comprehensive Incident Action Plan package\" -> EQUIVALENT (Score 1.0) | Reason: Contains the exact page number with explanatory text.\n"
            "- Ground Truth: \"Captain Rachel Brooks\" | Extracted: \"Planning Section Chief Captain Rachel Brooks\" -> EQUIVALENT (Score 1.0) | Reason: Correct person identified along with her role.\n"
            "- Ground Truth: \"Planning Section Chief\" | Extracted: \"Chief Captain\" -> PARTIAL (Score 0.5) | Reason: Contains the chief title but lacks full section specification.\n"
            "- Ground Truth: \"05/19/2026\" | Extracted: \"08/25/2025\" -> INCORRECT (Score 0.0) | Reason: Entirely different date.\n\n"
            f"Items to evaluate:\n{items_text}\n\n"
            "Respond ONLY with a valid JSON object adhering strictly to this schema:\n"
            "{\n"
            '  "evaluations": [\n'
            '    {\n'
            '      "path": "<Field Path>",\n'
            '      "verdict": "EQUIVALENT" | "PARTIAL" | "INCORRECT",\n'
            '      "score": 1.0 | 0.5 | 0.0,\n'
            '      "reason": "<one sentence explanation>"\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        payload = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096,
            },
        }

        if verbose:
            print(f"\n🤖 [LLM Judge ({model})] Evaluating {len(candidates)} mismatch candidate(s) in batch...")

        try:
            resp = requests.post(ollama_url, json=payload, timeout=90)
            resp.raise_for_status()
            resp_data = resp.json().get("response", "{}")
            parsed = json.loads(resp_data)
            eval_list = parsed.get("evaluations", [])

            results_by_path: Dict[str, Dict[str, Any]] = {}
            for item in eval_list:
                path = item.get("path")
                verdict = str(item.get("verdict", "INCORRECT")).upper()
                score = float(item.get("score", 0.0))
                # Validate score against verdict
                if verdict == "EQUIVALENT":
                    score = 1.0
                elif verdict == "PARTIAL":
                    score = 0.5
                else:
                    score = 0.0

                reason = item.get("reason", "")
                if path:
                    results_by_path[path] = {
                        "verdict": verdict,
                        "score": score,
                        "reason": reason,
                    }

            return results_by_path

        except Exception as e:
            if verbose:
                print(f"⚠️  [LLM Judge] Error during judge execution: {e}")
            return {}

    @staticmethod
    def calculate_accuracy(
        extracted: Any,
        ground_truth: Any,
        verbose: bool = True,
        fuzzy_threshold: float = 0.65,
        use_llm_judge: bool = True,
        judge_model: str = "qwen2.5:1.5b",
    ) -> float:
        """
        Main entry point for accuracy calculation.
        Performs recursive value comparison, queues string crosses for batched LLM evaluation,
        and computes the final accuracy score.
        """
        pending_candidates: List[Dict[str, Any]] = []
        leaf_scores: List[float] = []

        # Pass 1: Local recursive matching
        AccuracyCalculator._evaluate_node(
            extracted,
            ground_truth,
            path="root",
            pending_llm_candidates=pending_candidates,
            leaf_scores=leaf_scores,
            verbose=verbose,
            fuzzy_threshold=fuzzy_threshold,
        )

        # Pass 2: Batched LLM Judge fallback
        if use_llm_judge and pending_candidates:
            judge_results = AccuracyCalculator._run_batch_llm_judge(
                pending_candidates, model=judge_model, verbose=verbose
            )

            if verbose:
                print("\n--- 🤖 LLM Judge Verdicts ---")

            for candidate in pending_candidates:
                path = candidate["path"]
                leaf_idx = candidate["leaf_idx"]

                if path in judge_results:
                    res = judge_results[path]
                    verdict = res["verdict"]
                    score = res["score"]
                    reason = res["reason"]

                    leaf_scores[leaf_idx] = score

                    if verbose:
                        icon = "✅" if score == 1.0 else ("⚠️ " if score == 0.5 else "❌")
                        print(
                            f"  {icon} [{path}] -> {verdict} ({score:.1f})\n"
                            f"     Reason: {reason}\n"
                            f"     Extracted: \"{candidate['extracted']}\"\n"
                            f"     Expected:  \"{candidate['ground_truth']}\""
                        )
                else:
                    if verbose:
                        print(f"  ❌ [{path}] -> No verdict returned by LLM Judge, retained 0.0")

        # Compute overall final average score across all evaluated leaf fields
        final_accuracy = sum(leaf_scores) / len(leaf_scores) if leaf_scores else 0.0
        return final_accuracy
