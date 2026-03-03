"""
IncidentExtractor — single-pass canonical extraction with evidence attribution.

The canonical extraction pipeline is the foundation of the batch fill system.
Instead of asking the LLM to extract specific template fields N times (once per
agency form), the extractor runs ONE LLM call to extract a rich, template-agnostic
incident record from the transcript. Each extracted value carries an "evidence"
field containing the verbatim transcript quote that supports it, which is required
for chain-of-custody and legal compliance in emergency services reporting.

A second, much faster LLM call then maps the pre-extracted canonical record to
each specific template's field schema. Because the data is already structured,
the mapping call only needs to match field names — it does not re-read or
re-interpret the transcript. This makes the mapping calls fast and parallelizable.

Time complexity:
  Old (per-form extraction):   O(T * F) LLM calls  — T templates × F fields each
  New (canonical + mapping):   O(1 + T) LLM calls  — 1 extraction + T mappings
  For 5 agency forms at 10 fields each: 50 calls → 6 calls.
"""

import json
import os
import requests


# ── Canonical incident categories ─────────────────────────────────────────────
# These represent the full universe of information that may appear in an
# emergency incident transcript. Template-specific field names are mapped
# from these during the per-template mapping pass.

CANONICAL_CATEGORIES = [
    "reporting_officer",
    "badge_number",
    "unit_number",
    "case_number",
    "incident_type",
    "incident_date",
    "incident_time",
    "incident_location",
    "city",
    "jurisdiction",
    "narrative",
    "victim_names",
    "victim_ages",
    "victim_injuries",
    "suspect_names",
    "suspect_descriptions",
    "witness_names",
    "assisting_officers",
    "assisting_agencies",
    "actions_taken",
    "property_damage",
    "weapons_involved",
    "vehicle_descriptions",
    "medical_response",
    "hospital_transported_to",
    "follow_up_required",
]


class IncidentExtractor:
    """
    Extracts a canonical, template-agnostic incident record from an incident
    transcript in a single LLM call, then maps it to any number of agency-specific
    form templates without re-reading the original transcript.

    Each canonical field carries three sub-fields:
      value     — the extracted value (string, list, or null)
      evidence  — the verbatim transcript quote that supports this extraction
      confidence — "high" if clearly stated, "medium" if inferred, "low" if uncertain

    Usage (synchronous / sync batch):
        extractor = IncidentExtractor(transcript)
        canonical = extractor.extract_canonical()
        mapped = extractor.map_to_template(canonical, template.fields)

    Usage (async batch — preferred for POST /forms/fill/batch):
        canonical = await extractor.async_extract_canonical()
        results = await asyncio.gather(*[
            extractor.async_map_to_template(client, canonical, t.fields)
            for t in templates
        ])
    """

    def __init__(self, transcript: str):
        self._transcript = transcript
        self._ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self._ollama_url = f"{self._ollama_host}/api/generate"

    # ── Prompt builders ────────────────────────────────────────────────────────

    def _build_canonical_prompt(self) -> str:
        categories = json.dumps(CANONICAL_CATEGORIES, indent=2)
        return f"""You are an AI assistant specializing in emergency incident report analysis for law enforcement and fire services.

Your task is to extract every identifiable piece of information from the incident transcript below.

For every piece of information you extract, you MUST return three things:
  1. value     — the extracted value (use a JSON list if there are multiple values)
  2. evidence  — the exact verbatim quote from the transcript that supports this extraction
  3. confidence — "high" if the value is explicitly and clearly stated, "medium" if reasonably inferred from context, "low" if uncertain

Return ONLY a valid JSON object. No markdown, no explanation, no code fences.
Use null for the entire field object if a category is not mentioned in the transcript at all.

Categories to extract:
{categories}

Output format (example):
{{
  "reporting_officer": {{
    "value": "Officer Smith",
    "evidence": "Officer Smith reporting from unit 4",
    "confidence": "high"
  }},
  "victim_names": {{
    "value": ["Jane Doe", "Mark Smith"],
    "evidence": "victims Jane Doe and Mark Smith were treated on scene",
    "confidence": "high"
  }},
  "case_number": null
}}

Transcript:
{self._transcript}
"""

    def _build_mapping_prompt(self, canonical: dict, template_fields: dict) -> str:
        # Only pass the values (not evidence/confidence) to the mapping prompt
        # to keep it focused and fast
        canonical_values = {
            k: (v["value"] if isinstance(v, dict) and "value" in v else v)
            for k, v in canonical.items()
            if v is not None
        }
        return f"""You are mapping a pre-extracted incident record to a specific agency form template.
The incident data below was already extracted from a transcript — do NOT re-interpret anything.
Your ONLY task is to match the most semantically relevant value from the incident record to each template field.

Rules:
- Use only values from the provided incident record. Do not invent or infer new values.
- If a template field has no matching data in the incident record, use null.
- If a template field maps to a list value (e.g. multiple victims), join with "; ".
- Return ONLY a valid JSON object. No markdown, no explanation.

Pre-extracted incident record:
{json.dumps(canonical_values, indent=2)}

Template fields to fill (field name -> description/type):
{json.dumps(template_fields, indent=2)}

Output:
{{
  "template_field_name": "matched value or null",
  ...
}}
"""

    # ── JSON parsing helper ────────────────────────────────────────────────────

    def _parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip()
        return json.loads(raw)

    # ── Synchronous API ────────────────────────────────────────────────────────

    def _post_ollama_sync(self, prompt: str) -> str:
        resp = requests.post(
            self._ollama_url,
            json={"model": "mistral", "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()

    def extract_canonical(self) -> dict:
        """
        Synchronous canonical extraction.

        Returns a dict of category -> {value, evidence, confidence} or None.
        All categories in CANONICAL_CATEGORIES that appear in the transcript
        are populated. Missing categories are null.
        """
        raw = self._post_ollama_sync(self._build_canonical_prompt())
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            return {}

    def map_to_template(self, canonical: dict, template_fields: dict) -> dict:
        """
        Maps a canonical extraction to a specific template.
        Returns field -> value dict ready for Filler.fill_form_with_data().
        """
        raw = self._post_ollama_sync(self._build_mapping_prompt(canonical, template_fields))
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            return {f: None for f in template_fields}

    # ── Async API (used by POST /forms/fill/batch) ────────────────────────────

    async def _post_ollama_async(self, client, prompt: str) -> str:
        import httpx
        resp = await client.post(
            self._ollama_url,
            json={"model": "mistral", "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()

    async def async_extract_canonical(self) -> dict:
        """
        Async canonical extraction via httpx.AsyncClient.
        Identical semantics to extract_canonical() but non-blocking.
        """
        import httpx
        async with httpx.AsyncClient(timeout=180.0) as client:
            raw = await self._post_ollama_async(client, self._build_canonical_prompt())
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            return {}

    async def async_map_to_template(
        self, client, canonical: dict, template_fields: dict
    ) -> dict:
        """
        Async template mapping. Designed to be called concurrently with
        asyncio.gather() across multiple templates after a single canonical
        extraction, so M agency forms are filled in O(1 + M) LLM calls
        instead of O(M * F) where F is the number of fields per form.
        """
        raw = await self._post_ollama_async(
            client, self._build_mapping_prompt(canonical, template_fields)
        )
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            return {f: None for f in template_fields}

    # ── Evidence report ────────────────────────────────────────────────────────

    @staticmethod
    def build_evidence_report(canonical: dict) -> dict:
        """
        Transforms the raw canonical extraction into a clean evidence report
        keyed by canonical category. Only includes fields where a value was
        successfully extracted. Used by GET /forms/batches/{id}/audit.

        Returns:
          {
            "reporting_officer": {
              "value": "Officer Smith",
              "evidence": "Officer Smith reporting from unit 4",
              "confidence": "high"
            },
            ...
          }
        """
        return {
            k: v
            for k, v in canonical.items()
            if v is not None
            and isinstance(v, dict)
            and v.get("value") is not None
        }
