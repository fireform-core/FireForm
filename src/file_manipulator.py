import os
from src.filler import Filler
from src.llm import LLM
from src.translator import Translator
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
        Translates the raw user input to English (if needed), then runs the LLM
        to extract data from the translated text.

        Returns:
            extracted_data (dict): Extracted field values.
            missing_fields (list): Fields that could not be extracted.
            detected_language (str): BCP-47 code of the source language
                (e.g. "fr", "ar", "en").
        """
        print("[1] Starting extraction process...")
        if existing_data is None:
            existing_data = {}

        # --- Translation step (Issue #107) ---
        translator = Translator()
        translated_input, detected_language = translator.translate_to_english(user_input)
        if detected_language != "en":
            print(
                f"[TRANSLATION] Detected language: '{detected_language}'. "
                "Input translated to English before LLM processing."
            )

        llm = LLM(transcript_text=translated_input, target_fields=fields, json=existing_data)
        llm.main_loop()
        return llm.get_data(), detected_language

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
