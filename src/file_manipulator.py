import os
from src.filler import Filler
from src.llm import LLM
from src.logger import setup_logger
from commonforms import prepare_form

logger = setup_logger(__name__)


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
        logger.info("Received request from frontend.")
        logger.info("PDF template path: %s", pdf_form_path)

        if not os.path.exists(pdf_form_path):
            logger.error("PDF template not found at %s", pdf_form_path)
            return None  # Or raise an exception

        logger.info("Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)

            logger.info("Process complete. Output saved to: %s", output_name)

            return output_name

        except Exception as e:
            logger.exception("An error occurred during PDF generation: %s", e)
            raise e
