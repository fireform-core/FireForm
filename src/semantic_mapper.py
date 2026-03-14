"""
Semantic Mapping Layer
----------------------
Matches extracted JSON keys to PDF form field names using:
  1. Explicit mappings from a per-template config
  2. Case-insensitive exact match
  3. Alias match (from template config)
  4. Fuzzy token-overlap (Jaccard similarity)
  5. Positional fallback for any remaining unmatched pairs

Returns a MappingResult with matched values, warnings, and a printable report.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class MappingResult:
    """Holds the outcome of one semantic mapping run."""

    matched: dict           # {pdf_field_name: value}  — semantically placed
    positional_values: list # values for JSON keys that had no semantic PDF match
    unmapped_json_keys: list
    unmapped_pdf_fields: list
    ambiguous: list         # [(json_key, [candidate_pdf_fields])]
    warnings: list          # human-readable warning strings

    def report(self) -> str:
        lines = [
            "=== Semantic Mapping Report ===",
            f"  Matched (semantic):   {len(self.matched)}",
            f"  Positional fallback:  {len(self.positional_values)}",
            f"  Unmapped JSON keys:   {len(self.unmapped_json_keys)}",
            f"  Unmapped PDF fields:  {len(self.unmapped_pdf_fields)}",
            f"  Ambiguous:            {len(self.ambiguous)}",
        ]
        if self.matched:
            lines.append("\n  Semantic matches:")
            for pdf_f, val in self.matched.items():
                lines.append(f"    {pdf_f!r}  ←  {val!r}")
        if self.ambiguous:
            lines.append("\n  Ambiguous (best candidate used):")
            for json_key, candidates in self.ambiguous:
                lines.append(f"    {json_key!r}  →  {candidates}")
        if self.unmapped_json_keys:
            lines.append("\n  Unmapped JSON keys (positional fallback):")
            for k in self.unmapped_json_keys:
                lines.append(f"    - {k!r}")
        if self.unmapped_pdf_fields:
            lines.append("\n  Unmapped PDF fields (left blank):")
            for f in self.unmapped_pdf_fields:
                lines.append(f"    - {f!r}")
        if self.warnings:
            lines.append("\n  Warnings:")
            for w in self.warnings:
                lines.append(f"    ⚠  {w}")
        lines.append("================================")
        return "\n".join(lines)


class SemanticMapper:
    """
    Maps extracted JSON keys to PDF widget field names.

    template_config schema (all keys optional):
    {
        "field_mappings": {"Employee's name": "EmployeeName"},
        "aliases":         {"Employee's name": ["name", "worker name"]},
        "required_fields": ["Employee's name", "Date"]
    }
    """

    FUZZY_THRESHOLD = 0.35          # Jaccard threshold for a fuzzy hit
    AMBIGUITY_MARGIN = 0.05         # Scores within this of the top are ambiguous

    def __init__(self, template_config: Optional[dict] = None):
        cfg = template_config or {}
        self._explicit: dict  = cfg.get("field_mappings", {})  # json_key → pdf_field
        self._aliases: dict   = cfg.get("aliases", {})         # json_key → [alias…]
        self._required: list  = cfg.get("required_fields", [])

    # ── public ───────────────────────────────────────────────────────────────

    def map(self, extracted: dict, pdf_field_names: list) -> MappingResult:
        """
        Match extracted JSON keys to PDF widget field names.

        Parameters
        ----------
        extracted       : dict returned by LLM.get_data()   {json_key: value}
        pdf_field_names : ordered list of PDF widget names (annot.T stripped)

        Returns
        -------
        MappingResult
        """
        matched: dict    = {}   # pdf_field_name → value
        used_pdf: set    = set()
        used_json: set   = set()
        ambiguous: list  = []
        warnings: list   = []

        # ── Pass 1: explicit config mappings ─────────────────────────────────
        for json_key, pdf_field in self._explicit.items():
            if (
                json_key in extracted
                and pdf_field in pdf_field_names
                and pdf_field not in used_pdf
            ):
                matched[pdf_field] = extracted[json_key]
                used_pdf.add(pdf_field)
                used_json.add(json_key)

        # ── Pass 2: exact / alias / fuzzy for remaining keys ─────────────────
        remaining_pdf = [f for f in pdf_field_names if f not in used_pdf]

        for json_key, value in extracted.items():
            if json_key in used_json:
                continue

            result = self._find_match(json_key, remaining_pdf)

            if result is None:
                continue  # will end up in positional fallback

            if isinstance(result, list):
                # ambiguous: multiple close candidates — use the first, warn
                ambiguous.append((json_key, result))
                best = result[0]
            else:
                best = result

            matched[best] = value
            used_pdf.add(best)
            used_json.add(json_key)
            remaining_pdf = [f for f in remaining_pdf if f != best]

        # ── Required-field warnings ───────────────────────────────────────────
        for req in self._required:
            if req not in used_json:
                warnings.append(f"Required field not mapped: {req!r}")

        unmapped_json   = [k for k in extracted if k not in used_json]
        unmapped_pdf    = [f for f in pdf_field_names if f not in used_pdf]
        positional_vals = [extracted[k] for k in unmapped_json]

        return MappingResult(
            matched=matched,
            positional_values=positional_vals,
            unmapped_json_keys=unmapped_json,
            unmapped_pdf_fields=unmapped_pdf,
            ambiguous=ambiguous,
            warnings=warnings,
        )

    # ── private ───────────────────────────────────────────────────────────────

    def _normalize(self, s: str) -> set:
        """Split camelCase/PascalCase, lowercase, strip punctuation, return token set."""
        # Insert space before each uppercase letter that follows a lowercase letter
        # so "EmployeeEmail" → "Employee Email"
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
        s = s.lower()
        s = re.sub(r"[^a-z0-9\s]", " ", s)
        return set(s.split())

    def _similarity(self, a: str, b: str) -> float:
        """Jaccard similarity between token sets of two strings."""
        ta = self._normalize(a)
        tb = self._normalize(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def _find_match(self, json_key: str, pdf_fields: list):
        """
        Returns
        -------
        str        : single unambiguous best match
        list[str]  : multiple candidates above threshold (ambiguous)
        None       : no match found
        """
        # 1. Exact match (case-insensitive)
        for pdf_f in pdf_fields:
            if json_key.strip().lower() == pdf_f.strip().lower():
                return pdf_f

        # 2. Alias exact match
        for alias in self._aliases.get(json_key, []):
            for pdf_f in pdf_fields:
                if alias.strip().lower() == pdf_f.strip().lower():
                    return pdf_f

        # 3. Fuzzy token-overlap — try json_key AND any aliases vs each pdf field
        candidates_to_try = [json_key] + self._aliases.get(json_key, [])
        scored = []
        for pdf_f in pdf_fields:
            best_score = max(
                self._similarity(c, pdf_f) for c in candidates_to_try
            )
            if best_score >= self.FUZZY_THRESHOLD:
                scored.append((best_score, pdf_f))

        if not scored:
            return None

        scored.sort(key=lambda x: -x[0])
        top_score = scored[0][0]
        top_candidates = [f for s, f in scored if top_score - s < self.AMBIGUITY_MARGIN]

        return top_candidates[0] if len(top_candidates) == 1 else top_candidates
