import os
from src.filler import Filler
from src.llm import LLM
from commonforms import prepare_form
from src.privacy import PrivacyManager

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
        print("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            return None  # Or raise an exception

        print("[3] Starting extraction and PDF filling process...")
        try:
            # --- PRIVACY INTERCEPTION START ---
            privacy = PrivacyManager()
            safe_input = privacy.tokenize(user_input)
            
            self.llm._target_fields = fields
            self.llm._transcript_text = safe_input
            
            # Execute LLM here
            self.llm.main_loop()
            tokenized_dict = self.llm.get_data()
            
            # Unmask data back to real values
            real_data_dict = privacy.detokenize(tokenized_dict)
            # --- PRIVACY INTERCEPTION END ---

            # Pass the unmasked dictionary to the filler
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, manual_data=real_data_dict)

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")

            return output_name

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            raise e
