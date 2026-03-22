import os
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse, BatchFormFill, BatchFormFillResponse, BatchResultItem
from api.db.repositories import create_form, get_template, get_form
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller
from src.llm import LLM
from src.filler import Filler

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post("/fill", response_model=FormFillResponse)
async def fill_form(form: FormFill, db: Session = Depends(get_db)):
    template = get_template(db, form.template_id)
    if not template:
        raise AppError("Template not found", status_code=404)

    if not os.path.exists(template.pdf_path):
        raise AppError(f"Template PDF not found: {template.pdf_path}", status_code=404)

    try:
        # Step 1: LLM Extraction (Async)
        llm = LLM(transcript_text=form.input_text, target_fields=template.fields)
        await llm.async_main_loop()
        extracted_data = llm.get_data()

        # Step 2: PDF Filling (Sync)
        # Using filler directly to avoid redundant extraction in controller
        filler = Filler()
        path = filler.fill_form_with_data(
            pdf_form=template.pdf_path,
            data=extracted_data
        )
    except Exception as e:
        raise AppError(f"Processing failed: {str(e)}", status_code=500)

    if not path or not os.path.exists(path):
        raise AppError("PDF generation failed.", status_code=500)

    submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
    return create_form(db, submission)


@router.post("/fill/batch", response_model=BatchFormFillResponse)
async def fill_batch(batch: BatchFormFill, db: Session = Depends(get_db)):
    if not batch.template_ids:
        raise AppError("template_ids must not be empty", status_code=400)

    templates = []
    for tid in batch.template_ids:
        tpl = get_template(db, tid)
        if not tpl or not os.path.exists(tpl.pdf_path):
            raise AppError(f"Template {tid} invalid or PDF missing", status_code=404)
        templates.append(tpl)

    # Step 1: LLM Extraction (Async - ONE call for all templates)
    merged_fields = {}
    for tpl in templates:
        if isinstance(tpl.fields, dict): merged_fields.update(tpl.fields)
        else:
            for f in tpl.fields: merged_fields[f] = f

    try:
        llm = LLM(transcript_text=batch.input_text, target_fields=merged_fields)
        await llm.async_main_loop()
        extracted_json = llm.get_data()
    except Exception as e:
        raise AppError(f"Extraction failed: {str(e)}", status_code=500)

    # Step 2: PDF Filling (Sync - per template)
    results = []
    success_count = 0
    filler = Filler()

    for tpl in templates:
        try:
            tpl_field_keys = list(tpl.fields.keys()) if isinstance(tpl.fields, dict) else tpl.fields
            tpl_data = {k: extracted_json.get(k) for k in tpl_field_keys}
            
            output_path = filler.fill_form_with_data(pdf_form=tpl.pdf_path, data=tpl_data)

            submission = FormSubmission(
                template_id=tpl.id, 
                input_text=batch.input_text, 
                output_pdf_path=output_path
            )
            saved = create_form(db, submission)
            
            results.append(BatchResultItem(
                template_id=tpl.id, 
                template_name=tpl.name, 
                success=True,
                submission_id=saved.id, 
                download_url=f"/forms/download/{saved.id}"
            ))
            success_count += 1
        except Exception as e:
            results.append(BatchResultItem(
                template_id=tpl.id, 
                template_name=tpl.name, 
                success=False, 
                error=str(e)
            ))

    return BatchFormFillResponse(
        total=len(templates), 
        succeeded=success_count, 
        failed=len(templates)-success_count, 
        results=results
    )


@router.get("/{submission_id}", response_model=FormFillResponse)
def get_submission(submission_id: int, db: Session = Depends(get_db)):
    submission = get_form(db, submission_id)
    if not submission:
        raise AppError("Submission not found", status_code=404)
    return submission


@router.get("/download/{submission_id}")
def download_filled_pdf(submission_id: int, db: Session = Depends(get_db)):
    submission = get_form(db, submission_id)
    if not submission:
        raise AppError("Submission not found", status_code=404)

    file_path = submission.output_pdf_path
    if not os.path.exists(file_path):
        raise AppError("PDF file not found on server", status_code=404)

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=os.path.basename(file_path)
    )