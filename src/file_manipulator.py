import os
from src.filler import Filler
from src.llm import LLM
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

    def extract_data(self, user_input: str, fields: dict, existing_data: dict = None):
        """
        Runs LLM to extract data. Returns extracted_data and missing_fields.
        """
        print("[1] Starting extraction process...")
        if existing_data is None:
            existing_data = {}
        
        llm = LLM(transcript_text=user_input, target_fields=fields, json=existing_data)
        llm.main_loop()
        return llm.get_data(), llm.get_missing_fields()

    def fill_pdf(self, answers: dict, pdf_form_path: str):
        """
        Receives extracted data and fills the PDF.
        """
        print(f"[2] Filling PDF template: {pdf_form_path}")
        if not os.path.exists(pdf_form_path):
            raise FileNotFoundError(f"PDF template not found at {pdf_form_path}")

        try:
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, answers=answers)

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")

            return output_name

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            raise e
