import os
import logging
from src.filler import Filler
from src.llm import LLM
from commonforms import prepare_form
from src.utils.extraction_validator import ExtractionValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and store it.
        """
        template_path = pdf_path[:-4] + "_template.pdf"
        prepare_form(pdf_path, template_path)
        return template_path

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        """
        Receives raw data, runs extraction + validation + PDF filling,
        and returns the output file path with review flag.
        """
        logger.info("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            return None, True

        logger.info("[3] Starting extraction...")

        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input

            success = self.llm.extract_structured_safe()

            if not success:
                print("Structured extraction failed → fallback to old extraction")
                self.llm.main_loop()

            extracted_data = self.llm.get_data()

            validator = ExtractionValidator()
            validation_result = validator.validate(extracted_data)

            review_flag = validation_result["requires_review"]

            print("\n[4] Validation Result")
            print(validation_result)

            output_name = self.filler.fill_form(
                pdf_form=pdf_form_path,
                llm=self.llm
            )

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")

            return output_name, review_flag

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            raise e