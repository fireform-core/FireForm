import os
from src.filler import Filler
from src.llm import LLM
from src.validator import (
    validate_transcript,
    validate_template_fields,
    validate_all_inputs,
    ValidationException,
    ValidationError as ValidatorError
)
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

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns the path to the newly created file.

        Validates all inputs before processing to catch errors early.
        """
        print("[1] Received request from frontend.")
        print("[2] Validating inputs...")

        # Validate transcript/user input
        transcript_errors = validate_transcript(user_input)
        if transcript_errors:
            error_msg = f"Invalid transcript: {'; '.join(transcript_errors)}"
            print(f"[ERROR] {error_msg}")
            raise ValueError(error_msg)

        # Validate template fields
        field_errors = validate_template_fields(fields)
        if field_errors:
            error_msg = f"Invalid template fields: {'; '.join(field_errors)}"
            print(f"[ERROR] {error_msg}")
            raise ValueError(error_msg)

        print(f"[3] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            return None  # Or raise an exception

        print("[4] Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")

            return output_name

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            # Re-raise the exception so the frontend can handle it
            raise e
