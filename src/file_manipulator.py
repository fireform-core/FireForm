import os
from src.filler import Filler
from src.llm import LLM
from commonforms import prepare_form
import logging

logger = logging.getLogger(__name__)

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
        """
        logger.info("[1] Received request from frontend.")
        logger.info(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            logger.error(f"Error: PDF template not found at {pdf_form_path}")
            return None  # Or raise an exception

        logger.info("[3] Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)

            logger.info("\n----------------------------------")
            logger.info("✅ Process Complete.")
            logger.info(f"Output saved to: {output_name}")

            return output_name

        except Exception as e:
            logger.error(f"An error occurred during PDF generation: {e}", exc_info=True)
            # Re-raise the exception so the frontend can handle it
            raise e
