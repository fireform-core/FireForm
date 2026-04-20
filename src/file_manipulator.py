import logging
import os
import platform
from src.filler import Filler
from src.llm import LLM

logger = logging.getLogger("fireform.file_manipulator")

class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        # Lazy import
        from commonforms import prepare_form
        template_path = pdf_path[:-4] + "_template.pdf"

        if platform.system() == "Windows":
           os.system("taskkill /F /IM ollama.exe >nul 2>&1")
           logger.info("Cleared existing Ollama instances on Windows.")
        
        
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

        print("[3] Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)

            logger.info("Starting extraction and PDF filling process...")
            logger.info("Process complete. Output saved to: %s", output_name)
            logger.exception("An error occurred during PDF generation: %s", e)

            return output_name

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            # Re-raise the exception so the frontend can handle it
            raise e
