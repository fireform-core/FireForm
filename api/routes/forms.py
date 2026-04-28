import os

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormBatchFill, FormBatchFillResponse, FormFill, FormFillResponse
from api.db.repositories import create_form, get_template, get_templates_by_ids
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    fetched_template = get_template(db, form.template_id)
    if not fetched_template:
        raise AppError("Template not found", status_code=404)

    controller = Controller()
    path = controller.fill_form(
        user_input=form.input_text,
        fields=fetched_template.fields,
        pdf_form_path=fetched_template.pdf_path,
    )

    submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
    return create_form(db, submission)


@router.post("/fill-batch", response_model=FormBatchFillResponse)
def fill_forms_batch(form: FormBatchFill, db: Session = Depends(get_db)):
    templates = get_templates_by_ids(db, form.template_ids)
    if not templates:
        raise AppError("No templates found for provided template_ids", status_code=404)

    template_ids_found = {tpl.id for tpl in templates}
    template_ids_missing = [tid for tid in form.template_ids if tid not in template_ids_found]
    if template_ids_missing:
        raise AppError(
            f"Template(s) not found: {template_ids_missing}",
            status_code=404,
        )

    controller = Controller()
    batch_result = controller.fill_multiple_forms(
        incident_record=form.incident_record,
        templates=templates,
    )

    batch_id = batch_result["batch_id"]
    return {
        **batch_result,
        "download_url": f"/forms/batch-download/{batch_id}",
    }


@router.get("/batch-download/{batch_id}")
def download_batch_package(batch_id: str):
    zip_path = os.path.join("src", "outputs", "batches", f"{batch_id}.zip")
    if not os.path.exists(zip_path):
        raise AppError("Batch package not found", status_code=404)

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"{batch_id}.zip",
    )


