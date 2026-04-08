from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from src.validator import validate_incident
from datetime import datetime


class FormValidationError(Exception):
    """Raised when incident data validation fails before PDF filling."""

    def __init__(self, errors: list[str], data: dict = None):
        self.errors = errors
        self.data = data
        message = f"Validation failed with {len(errors)} error(s): {'; '.join(errors)}"
        super().__init__(message)


class Filler:
    def __init__(self, skip_validation: bool = False):
        """
        Initialize the Filler.

        Args:
            skip_validation: If True, skips input validation. Use with caution.
        """
        self.skip_validation = skip_validation

    def fill_form(self, pdf_form: str, llm: LLM, required_fields: list[str] | None = None):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in the visual order (top-to-bottom, left-to-right).

        Args:
            pdf_form: Path to the PDF template.
            llm: LLM instance with transcript and target fields set.
            required_fields: Optional list of fields that must be present and valid.

        Raises:
            FormValidationError: If extracted data fails validation.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Generate dictionary of answers from your original function
        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()  # This is a dictionary

        # Validate extracted data before PDF filling
        if not self.skip_validation:
            print("[VALIDATION] Validating extracted incident data...")
            validation_errors = validate_incident(textbox_answers, required_fields)

            if validation_errors:
                print(f"[VALIDATION FAILED] {len(validation_errors)} error(s) found:")
                for error in validation_errors:
                    print(f"  - {error}")
                raise FormValidationError(errors=validation_errors, data=textbox_answers)

            print("[VALIDATION PASSED] All required fields are valid.")

        answers_list = list(textbox_answers.values())

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Loop through pages
        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                i = 0
                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        if i < len(answers_list):
                            annot.V = f"{answers_list[i]}"
                            annot.AP = None
                            i += 1
                        else:
                            # Stop if we run out of answers
                            break

        PdfWriter().write(output_pdf, pdf)

        # Your main.py expects this function to return the path
        return output_pdf
