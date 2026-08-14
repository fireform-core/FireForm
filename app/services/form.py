import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app.core.config import BASE_DIR
from app.core.errors.base import AppError
from app.db.repositories import (
    create_form,
    delete_form_submission,
    get_submissions,
    get_submissions_before,
    get_submissions_with_template,
)
from app.models import FormSubmission, Template
from app.services.controller import Controller
from app.services.input import InputService

PROJECT_ROOT = BASE_DIR

_STOPWORDS = {
    "the", "and", "a", "of", "to", "in", "is", "that", "it", "was", "for", "on",
    "as", "with", "by", "at", "an", "be", "this", "are", "from", "or", "have",
    "has", "had", "but", "not", "he", "she", "they", "we", "i", "you", "my", "his",
    "her", "their", "our", "me", "him", "them", "us", "about", "there", "their",
    "were", "been", "would", "could", "should", "will", "can", "no", "yes", "any",
    "so", "very", "patient", "presents", "with", "reported", "history", "shows",
    "left", "right", "pain", "due", "after", "before", "emergency", "department",
    "medical", "clinical"
}


def _resolve_project_file(file_path: str) -> Path:
    raw_path = (file_path or "").strip()
    if not raw_path:
        raise AppError("Path is required", status_code=400)

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise AppError("Path must be inside the project", status_code=400)

    return candidate


class FormService:
    def __init__(self):
        self.controller = Controller()
        self.input_service = InputService()

    def fill_form(
        self, session: Session, template: Template, input_id: UUID, model: str | None = None
    ) -> FormSubmission:
        transcript = self.input_service.resolve_transcript(session, input_id)
        return self.fill_and_persist(session, template, transcript, input_id, model)

    def fill_and_persist(
        self,
        session: Session,
        template: Template,
        transcript: str,
        input_id: UUID,
        model: str | None = None,
    ) -> FormSubmission:
        path = self.controller.fill_form(
            user_input=transcript,
            fields=template.fields,
            pdf_form_path=template.pdf_path,
            model=model,
        )

        extracted_fields = self.controller.file_manipulator.llm._json

        submission = FormSubmission(
            template_id=template.id,
            input_id=input_id,
            input_text=transcript,
            extracted_fields=extracted_fields,
            output_pdf_path=path,
        )
        return create_form(session, submission)

    def list_submissions(self, session: Session) -> list[dict]:
        results = get_submissions(session)
        return [
            {
                "id": sub.id,
                "template_id": sub.template_id,
                "template_name": name or "Unknown Template",
                "input_text": sub.input_text,
                "output_pdf_path": sub.output_pdf_path,
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
            }
            for sub, name in results
        ]

    def get_analytics(self, session: Session) -> dict:
        results = get_submissions_with_template(session)

        total_submissions = len(results)

        template_counts = Counter()
        daily_counts = Counter()
        words = []

        for sub, name in results:
            template_name = name or "Unknown Template"
            template_counts[template_name] += 1

            if sub.created_at:
                date_str = sub.created_at.strftime("%Y-%m-%d")
                daily_counts[date_str] += 1

            if sub.input_text:
                found_words = re.findall(r"\b[a-zA-Z]{3,15}\b", sub.input_text.lower())
                for w in found_words:
                    if w not in _STOPWORDS:
                        words.append(w)

        sorted_daily = [{"date": k, "count": v} for k, v in sorted(daily_counts.items())]
        sorted_templates = [{"template_name": k, "count": v} for k, v in template_counts.most_common()]
        common_terms = [{"word": k, "count": v} for k, v in Counter(words).most_common(12)]

        return {
            "total_submissions": total_submissions,
            "by_template": sorted_templates,
            "by_date": sorted_daily,
            "common_terms": common_terms,
        }

    def purge_submissions(self, session: Session, retention_days: int) -> int:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        submissions = get_submissions_before(session, cutoff_date)

        purged_count = 0
        for sub in submissions:
            if sub.output_pdf_path:
                try:
                    resolved_out = _resolve_project_file(sub.output_pdf_path)
                    if resolved_out.exists() and resolved_out.is_file():
                        resolved_out.unlink()
                except Exception:
                    pass
            delete_form_submission(session, sub)
            purged_count += 1

        return purged_count
