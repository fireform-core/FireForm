import os
from src.filler import Filler
from src.llm import LLM
from src.batch_orchestrator import BatchOrchestrator


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()
        self.batch_orchestrator = BatchOrchestrator(self.filler.fill_form_from_record)

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        from commonforms import prepare_form

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

    def fill_multiple_forms(self, incident_record: dict, templates: list):
        """Fill multiple templates from one structured incident record."""
        print("[BATCH] Received request for multi-document generation.")
        print(f"[BATCH] Templates requested: {len(templates)}")

        return self.batch_orchestrator.run_batch(
            incident_record=incident_record,
            templates=templates,
        )
