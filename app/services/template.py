from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from app.api.schemas.templates import (
    ExtractedField,
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
    list_templates as repo_list_templates,
)
from app.models import Template
from app.services.form_filler.template import create_template as extract_pdf_template


class TemplateService:
    def __init__(self):
        pass

    def _calculate_field_count(self, fields: dict | None, pdf_path: str = "") -> int | None:

        if not fields:
            if pdf_path:
                return _count_pdf_widgets(pdf_path)
            return 0
        if isinstance(fields, dict) and "schema" in fields and isinstance(fields["schema"], dict):
            props = fields["schema"].get("properties", {})
            count = 0
            for prop in props.values():
                if isinstance(prop, dict) and prop.get("type") == "array":
                    count += len(prop.get("items", {}).get("properties", {}))
                else:
                    count += 1
            return count
        if isinstance(fields, dict):
            return len(fields)
        return _count_pdf_widgets(pdf_path) if pdf_path else 0

    def list_templates(self, session: Session) -> list[TemplateResponse]:
        templates = repo_list_templates(session)
        return [
            TemplateResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                pdf_path=t.pdf_path,
                fields=t.fields,
                field_count=self._calculate_field_count(t.fields, t.pdf_path),
            )
            for t in templates
        ]

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

        try:
            schema, tables, groups = extract_pdf_template(str(target_path))
            fields_list: list[ExtractedField] = []
            for name, prop in schema.get("properties", {}).items():
                if prop.get("type") == "array":
                    sub_props = prop.get("items", {}).get("properties", {})
                    for col_name, col_prop in sub_props.items():
                        fields_list.append(
                            ExtractedField(
                                name=f"{name}.{col_name}",
                                description=col_prop.get("description", "") or col_name,
                                type=col_prop.get("type", "string"),
                            )
                        )
                else:
                    fields_list.append(
                        ExtractedField(
                            name=name,
                            description=prop.get("description", "") or name,
                            type=prop.get("type", "string"),
                        )
                    )
            field_count = len(fields_list)
            schema_data = schema
            tables_data = tables
        except Exception:
            extracted = _extract_pdf_fields(relative_path)
            fields_list = [
                ExtractedField(
                    name=f["name"],
                    description=f.get("description", ""),
                    type=f.get("type", "string"),
                )
                for f in (extracted or [])
            ]
            field_count = len(fields_list) if extracted is not None else None
            schema_data = None
            tables_data = None

        return TemplateUploadResponse(
            filename=target_path.name,
            pdf_path=relative_path,
            field_count=field_count,
            fields=fields_list,
            schema_data=schema_data,
            tables=tables_data,
        )

    def create_template(self, session: Session, template: TemplateCreate) -> TemplateResponse:
        fields = template.fields
        resolved_pdf = self.resolve_pdf_path(template.pdf_path)

        if not fields and resolved_pdf.exists():
            try:
                schema, tables, groups = extract_pdf_template(str(resolved_pdf))
                fields = {"schema": schema, "tables": tables, "groups": groups}
            except Exception:
                fields = {}

        tpl = Template(name=template.name, pdf_path=template.pdf_path, fields=fields)
        created = create_template(session, tpl)
        return TemplateResponse(
            id=created.id,
            name=created.name,
            description=created.description,
            pdf_path=created.pdf_path,
            fields=created.fields,
            field_count=self._calculate_field_count(created.fields, created.pdf_path),
        )


    def make_fillable(self, resolved_pdf_path: str) -> MakeFillableResponse:
        template_path = resolved_pdf_path[:-4] + "_template.pdf"
        try:
            import os
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
            from commonforms import prepare_form
            prepare_form(resolved_pdf_path, template_path)
        except Exception:
            template_path = resolved_pdf_path

        new_path = Path(template_path)
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
