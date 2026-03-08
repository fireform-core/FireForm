import os
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse
from api.db.repositories import create_form, get_template, get_form
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    # Single DB query (fixes issue #149 - redundant query)
    template = get_template(db, form.template_id)
    if not template:
        raise AppError("Template not found", status_code=404)

    try:
        controller = Controller()
        # FileManipulator.fill_form expects fields as a list of key strings
        path = controller.fill_form(
            user_input=form.input_text,
            fields=template.fields,  # Passes dict directly
            pdf_form_path=template.pdf_path
        )
    except ConnectionError:
        raise AppError(
            "Could not connect to Ollama. Make sure ollama serve is running.",
            status_code=503
        )
    except Exception as e:
        raise AppError(f"PDF filling failed: {str(e)}", status_code=500)

    # Guard: controller returned None instead of a file path
    if not path:
        raise AppError(
            "PDF generation failed — no output file was produced. "
            "Check that the PDF template is a valid fillable form and Ollama is running.",
            status_code=500
        )

    if not os.path.exists(path):
        raise AppError(
            f"PDF was generated but file not found at: {path}",
            status_code=500
        )

    submission = FormSubmission(
        **form.model_dump(),
        output_pdf_path=path
    )
    return create_form(db, submission)


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