from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from app.api.schemas.templates import (
    MakeFillableResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUploadResponse,
)
from app.core import paths
from app.core.pdf_utils import _count_pdf_widgets, _extract_pdf_fields
from app.db.repositories import (
    create_template,
    delete_template,
    get_jobs_by_template,
    get_submissions_by_template,
    list_templates,
)
from app.models import Template
from app.services.controller import Controller


class TemplateService:
    def __init__(self):
        self.controller = Controller()

    def list_templates(self, session: Session) -> list[Template]:
        return list_templates(session)

    def resolve_pdf_path(self, path: str) -> Path:
        return paths._resolve_project_file(path)

    def save_uploaded_pdf(self, directory: str, filename: str, content: bytes) -> TemplateUploadResponse:
        target_dir = paths._resolve_target_directory(directory)
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / filename
        if target_path.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            target_path = target_dir / f"{target_path.stem}_{timestamp}{target_path.suffix}"

        with target_path.open("wb") as output_file:
            output_file.write(content)

        relative_path = target_path.relative_to(paths.PROJECT_ROOT).as_posix()
        extracted = _extract_pdf_fields(relative_path)
        return TemplateUploadResponse(
            filename=target_path.name,
            pdf_path=relative_path,
            field_count=None if extracted is None else len(extracted),
            fields=extracted or [],
        )

    def create_template(self, session: Session, template: TemplateCreate) -> TemplateResponse:
        tpl = Template(**template.model_dump())
        created = create_template(session, tpl)
        return TemplateResponse(
            id=created.id,
            name=created.name,
            pdf_path=created.pdf_path,
            fields=created.fields,
            field_count=_count_pdf_widgets(created.pdf_path),
        )

    def make_fillable(self, resolved_pdf_path: str) -> MakeFillableResponse:
        new_absolute = self.controller.prepare_fillable(resolved_pdf_path)
        new_path = Path(new_absolute)
        if not new_path.is_absolute():
            new_path = (paths.PROJECT_ROOT / new_path).resolve()
        relative_path = new_path.relative_to(paths.PROJECT_ROOT).as_posix()

        return MakeFillableResponse(
            pdf_path=relative_path,
            field_count=_count_pdf_widgets(relative_path),
        )

    def delete_template(self, session: Session, template: Template) -> None:
        # Batched like the original route: only session.delete() per row here,
        # single commit at the end (via the delete_template repo call) so the
        # cascade stays atomic instead of partially committing on failure.
        submissions = get_submissions_by_template(session, template.id)
        for sub in submissions:
            if sub.output_pdf_path:
                try:
                    resolved_out = paths._resolve_project_file(sub.output_pdf_path)
                    if resolved_out.exists() and resolved_out.is_file():
                        resolved_out.unlink()
                except Exception:
                    pass
            session.delete(sub)

        jobs = get_jobs_by_template(session, template.id)
        for job in jobs:
            session.delete(job)

        if template.pdf_path:
            try:
                resolved_pdf = paths._resolve_project_file(template.pdf_path)
                if resolved_pdf.exists() and resolved_pdf.is_file():
                    resolved_pdf.unlink()
            except Exception:
                pass

        delete_template(session, template)
