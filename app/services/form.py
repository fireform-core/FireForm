import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session

from app.core import paths
from app.core.errors.base import AppError
from app.db.repositories import (
    create_form,
    delete_form_submission,
    get_submissions,
    get_submissions_before,
    get_submissions_with_template,
)
from app.models import FormSubmission, Template
from app.services.form_filler import filler
from app.services.input import InputService

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


class FormService:
    def __init__(self):
        self.input_service = InputService()

    def fill_form(
        self,
        session: Session,
        template: Template,
        input_id: UUID | None = None,
        input_text: str | None = None,
        model: str | None = None,
    ) -> FormSubmission:
        if input_id is not None and not input_text:
            transcript = self.input_service.resolve_transcript(session, input_id)
        elif input_text:
            transcript = input_text
            if input_id is None:
                from app.api.schemas.enums import InputStatus, InputType
                from app.models import Input
                input_record = Input(
                    input_type=InputType.text,
                    status=InputStatus.ready,
                    transcript=input_text,
                    character_count=len(input_text),
                    word_count=len(input_text.split()),
                )
                session.add(input_record)
                session.commit()
                session.refresh(input_record)
                input_id = input_record.input_id
        else:
            raise AppError("Either input_id or input_text is required", status_code=422, error_code="VALIDATION_ERROR")
        return self.fill_and_persist(session, template, transcript, input_id, model)

    def fill_and_persist(
        self,
        session: Session,
        template: Template,
        transcript: str,
        input_id: UUID,
        model: str | None = None,
    ) -> FormSubmission:
        resolved_pdf = paths._resolve_project_file(template.pdf_path)
        if not resolved_pdf.exists():
            raise FileNotFoundError(f"PDF template not found at {template.pdf_path}")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_name = f"{resolved_pdf.stem}_{timestamp}_filled.pdf"
        out_target = resolved_pdf.parent / out_name

        filler.fill(
            pdf_path=str(resolved_pdf),
            narrative=transcript,
            out_path=str(out_target),
            model=model,
        )

        relative_out = out_target.relative_to(paths.PROJECT_ROOT).as_posix()

        submission = FormSubmission(
            template_id=template.id,
            input_id=input_id,
            input_text=transcript,
            output_pdf_path=relative_out,
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
                    resolved_out = paths._resolve_project_file(sub.output_pdf_path)
                    if resolved_out.exists() and resolved_out.is_file():
                        resolved_out.unlink()
                except Exception:
                    pass
            delete_form_submission(session, sub)
            purged_count += 1

        return purged_count
