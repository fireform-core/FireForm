import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.schemas.wizard import DetectFieldsResponse
from src.controller import Controller

router = APIRouter(prefix="/wizard", tags=["wizard"])


@router.post("/detect-fields", response_model=DetectFieldsResponse)
async def detect_fields(file: UploadFile = File(...)):
    """Upload a PDF and detect all interactive form fields.

    Parses the PDF's /Annots annotations for /Widget subtypes and
    returns each field's name, type (Text, Button, Choice), and
    bounding box coordinates (X, Y, Width, Height).

    This endpoint powers the Field Mapping Wizard, enabling
    non-technical users to see all fillable fields in a PDF
    before mapping them to FireForm's data schema.

    **Supported field types:**
    - Text (/Tx): Text inputs and text areas
    - Button (/Btn): Checkboxes and radio buttons
    - Choice (/Ch): Dropdowns and list boxes

    **Note:** Only digitally created fillable PDFs (AcroForms) are
    supported. Scanned/image-based PDFs will return zero fields.
    """
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="A PDF filename is required.")

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        content = await file.read()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        controller = Controller()
        result = controller.detect_fields(tmp_path)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process PDF: {str(e)}",
        )
    finally:
        # Clean up temp file
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except (NameError, OSError):
            pass

    return result
