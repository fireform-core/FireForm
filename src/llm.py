import json
import logging
import os

import requests

from src.schemas.incident_report import IncidentReport


logger = logging.getLogger(__name__)


class LLM:
    def __init__(self, transcript_text=None, target_fields=None):
        self._transcript_text = transcript_text
        # target_fields kept for backward compatibility with FileManipulator;
        # new extraction uses IncidentReport.llm_schema_hint() instead.
        self._target_fields = target_fields
        self._result: IncidentReport | None = None

    def build_prompt(self) -> str:
        """
        Build a single structured prompt for Ollama's /api/generate endpoint.

        Uses IncidentReport.llm_schema_hint() as the schema constraint so the
        model always returns a JSON object with the correct field names.
        """
        schema_hint = json.dumps(IncidentReport.llm_schema_hint(), indent=2)
        system = (
            "You are an AI assistant that extracts structured incident report data "
            "from transcribed voice recordings made by first responders.\n\n"
            "Return ONLY a valid JSON object that matches the schema below. "
            "Do not include any explanation, markdown code fences, or extra text.\n\n"
            f"Schema:\n{schema_hint}\n\n"
            "Rules:\n"
            "  - The transcript may contain ASR errors (misspellings, repeated words, partial phrases). "
            "Use only high-confidence information explicitly present in the transcript.\n"
            "  - Set a field to null if the information is not present in the transcript.\n"
            "  - If two values conflict, choose null unless one value is clearly confirmed later.\n"
            "  - For list fields (e.g. unit_ids, personnel), return a JSON array.\n"
            "  - For integer/float fields, return numeric JSON values (not strings).\n"
            "  - For incident_type, prefer short lowercase labels like wildfire, structure_fire, "
            "vehicle_accident, ems, hazmat, rescue when clearly supported by transcript language.\n"
            "  - For timestamps, reproduce the exact phrasing from the transcript "
            "(e.g. '14:35', '1435 hours', '2:35 PM').\n"
            "  - Do not invent or infer values that are not explicitly stated.\n"
            "  - Never output keys that are not present in the schema."
        )
        user = (
            "Extract all incident report fields from the following transcript:\n\n"
            f"{self._transcript_text}"
        )
        return f"[INST] {system}\n\n{user} [/INST]"

    def _ollama_url(self) -> str:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        return f"{host}/api/generate"

    def main_loop(self) -> "LLM":
        """
        Send a single structured request to Ollama and parse response as an
        IncidentReport. Fields that remain unextracted are listed in
        IncidentReport.requires_review.
        """
        prompt = self.build_prompt()
        model = os.getenv("OLLAMA_MODEL", "mistral")
        payload = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        }

        try:
            response = requests.post(self._ollama_url(), json=payload)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Could not connect to Ollama at {self._ollama_url()}. "
                "Please ensure Ollama is running and accessible."
            )
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Ollama returned an error: {e}") from e

        raw = response.json()["response"]
        try:
            extracted = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(
                "Ollama returned invalid JSON: %s. Raw (first 200 chars): %.200s",
                e,
                raw,
            )
            extracted = {}

        self._result = IncidentReport(**extracted)
        logger.info("Extraction complete. requires_review: %s", self._result.requires_review)
        return self

    def get_data(self) -> dict:
        """
        Return extracted data as plain dict for PDF filler.
        Pipeline metadata (requires_review) is excluded.
        """
        if self._result is None:
            return {}
        return self._result.model_dump(exclude={"requires_review"})

    def get_report(self) -> IncidentReport | None:
        """Return full incident report including requires_review."""
        return self._result
