import os
from src.filler import Filler
from src.llm import LLM
from src.validator import validate_incident
from commonforms import prepare_form


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        template_path = pdf_path[:-4] + "_template.pdf"
        prepare_form(pdf_path, template_path)
        return template_path

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str) -> str:
        """
        Orchestrates the full extract → validate → fill pipeline.

        Steps:
            1. Run LLM extraction to convert raw incident text into a
               structured field dict.
            2. Validate the extracted dict before touching any PDF.
               Raises ``ValueError`` if required incident fields are
               missing or empty.
            3. Pass validated data to the Filler to produce the output PDF.

        Args:
            user_input: Free-form incident description (voice transcript or
                        typed text).
            fields:     Template field schema passed to the LLM as extraction
                        targets.
            pdf_form_path: Path to the fillable PDF template.

        Returns:
            Path to the filled output PDF.

        Raises:
            FileNotFoundError: If the PDF template does not exist.
            ValueError: If extracted incident data fails validation.
        """
        print("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            raise FileNotFoundError(
                f"PDF template not found: {pdf_form_path}"
            )

        print("[3] Running LLM extraction...")
        self.llm._target_fields = fields
        self.llm._transcript_text = user_input
        extracted = self.llm.main_loop().get_data()

        print("[4] Validating extracted incident data...")
        errors = validate_incident(extracted)
        if errors:
            raise ValueError(
                "Extracted incident data failed validation:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        print("[5] Filling PDF with validated data...")
        output_name = self.filler.fill_form(pdf_form=pdf_form_path, data=extracted)

        print("\n----------------------------------")
        print("✅ Process Complete.")
        print(f"Output saved to: {output_name}")

        return output_name
