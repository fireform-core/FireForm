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
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    template = get_template(db, form.template_id)
    if not template:
        raise AppError("Template not found", status_code=404)

    # Validate PDF exists on disk (#235)
    if not os.path.exists(template.pdf_path):
        raise AppError(
            f"Template PDF not found on disk: {template.pdf_path}. "
            "Please re-upload the template.",
            status_code=404
        )

    try:
        controller = Controller()
        fields_list = list(template.fields.keys()) if isinstance(template.fields, dict) else template.fields
        path = controller.fill_form(
            user_input=form.input_text,
            fields=fields_list,
            pdf_form_path=template.pdf_path
        )
    except ConnectionError:
        raise AppError(
            "Could not connect to Ollama. Make sure ollama serve is running.",
            status_code=503
        )
    except Exception as e:
        raise AppError(f"PDF filling failed: {str(e)}", status_code=500)

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


@router.post("/fill/batch", response_model=BatchFormFillResponse)
def fill_batch(batch: BatchFormFill, db: Session = Depends(get_db)):
    """
    Batch multi-template form filling — closes #156.

    KEY DESIGN: LLM extraction runs ONCE for the entire batch.
    All templates share the same extracted JSON — no redundant Ollama calls.

    Flow:
      1. Validate all templates exist upfront
      2. Merge ALL fields from ALL templates into one superset
      3. ONE LLM call extracts all values from transcript
      4. Each template PDF filled using its relevant subset of extracted values
    """
    if not batch.template_ids:
        raise AppError("template_ids must not be empty", status_code=400)

    # ── Step 1: Validate all templates upfront ────────────────
    templates = []
    for tid in batch.template_ids:
        tpl = get_template(db, tid)
        if not tpl:
            raise AppError(f"Template {tid} not found", status_code=404)
        if not os.path.exists(tpl.pdf_path):
            raise AppError(
                f"Template '{tpl.name}' (id={tid}) PDF not found on disk. "
                "Please re-upload the template.",
                status_code=404
            )
        templates.append(tpl)

    print(f"[BATCH] Starting batch fill for {len(templates)} template(s)...")
    print(f"[BATCH] Templates: {[t.name for t in templates]}")

    # ── Step 2: Merge ALL fields from ALL templates into superset
    # One LLM call covers every field needed across all templates
    merged_fields = {}
    for tpl in templates:
        if isinstance(tpl.fields, dict):
            merged_fields.update(tpl.fields)
        else:
            for f in tpl.fields:
                merged_fields[f] = f

    print(f"[BATCH] Merged superset: {len(merged_fields)} unique field(s) across all templates")

    # ── Step 3: ONE LLM call for entire batch ─────────────────
    print(f"[BATCH] Running single LLM extraction (no redundant calls)...")
    try:
        llm = LLM(
            transcript_text=batch.input_text,
            target_fields=merged_fields
        )
        llm.main_loop()
        extracted_json = llm.get_data()
        print(f"[BATCH] Extraction complete — {len(extracted_json)} fields extracted")
    except ConnectionError:
        raise AppError(
            "Could not connect to Ollama. Make sure ollama serve is running.",
            status_code=503
        )
    except Exception as e:
        raise AppError(f"LLM extraction failed: {str(e)}", status_code=500)

    # ── Step 4: Fill each PDF with pre-extracted data ─────────
    # No new LLM calls — just PDF writing per template
    results = []
    success_count = 0
    fail_count = 0
    filler = Filler()

    for tpl in templates:
        print(f"[BATCH] Filling PDF: '{tpl.name}' (id={tpl.id})...")
        try:
            # Subset extracted data to only this template's fields
            tpl_field_keys = list(tpl.fields.keys()) if isinstance(tpl.fields, dict) else tpl.fields
            tpl_data = {k: extracted_json.get(k) for k in tpl_field_keys}

            # Fill PDF directly — no LLM call
            output_path = filler.fill_form_with_data(
                pdf_form=tpl.pdf_path,
                data=tpl_data
            )

            if not output_path or not os.path.exists(output_path):
                raise RuntimeError("No output file produced")

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
                download_url=f"/forms/download/{saved.id}",
                error=None
            ))
            success_count += 1
            print(f"[BATCH] ✅ '{tpl.name}' done (submission #{saved.id})")

        except Exception as e:
            fail_count += 1
            results.append(BatchResultItem(
                template_id=tpl.id,
                template_name=tpl.name,
                success=False,
                submission_id=None,
                download_url=None,
                error=str(e)
            ))
            print(f"[BATCH] ✗ '{tpl.name}' failed: {e}")

    print(f"[BATCH] Complete — {success_count} succeeded, {fail_count} failed")

    return BatchFormFillResponse(
        total=len(templates),
        succeeded=success_count,
        failed=fail_count,
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