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

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns (output_pdf_path, needs_review) where needs_review is a dict
        of {field_name: {suggested_value, confidence}} for human verification.
        """
        print("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            return None, {}  # Or raise an exception

        print("[3] Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input
            # filler.fill_form now returns a tuple: (output_pdf_path, needs_review)
            output_name, needs_review = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")
            if needs_review:
                print(f"⚠️  {len(needs_review)} field(s) flagged for human review: {list(needs_review.keys())}")

            return output_name, needs_review

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            raise e
