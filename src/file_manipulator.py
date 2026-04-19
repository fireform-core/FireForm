# file_manipulator.py 
import os
from src.filler import Filler
from src.llm import LLM
from commonforms import prepare_form


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        template_path = pdf_path[:-4] + "_template.pdf"
        prepare_form(pdf_path, template_path)
        return template_path

        #timeline field added
    def fill_form(self, user_input: str, definitions: list, pdf_fields: list, pdf_form_path: str, use_timeline: bool = False):
        print("[1] Received request from ag frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            return None

        print("[3] Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = definitions
            self.llm._pdf_fields = pdf_fields
            self.llm._transcript_text = user_input
            output_name = self.filler.fill_form(
                pdf_form=pdf_form_path,
                llm=self.llm,
                pdf_fields=pdf_fields,
                definitions=definitions,          #timeline field added
                use_timeline=use_timeline
            )

            print("\n----------------------------------")
            print(" Process Complete.")
            print(f"Output saved to: {output_name}")

            return output_name

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            raise e
