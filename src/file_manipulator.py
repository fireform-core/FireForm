import os
from pdfrw import PdfReader
from src.filler import Filler
from src.llm import LLM
from src.pdf_utils import decode_pdf_name
from commonforms import prepare_form
from sqlmodel import Session
from src.report_schema import ReportSchemaProcessor
from api.db.models import Template



class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        prepare_form(pdf_path, pdf_path)
        return pdf_path

    def extract_template_field_map(self, pdf_path: str) -> dict[str, str]:
        """AcroForm widget names from a PDF, each mapped to type ``string`` (Template.fields shape)."""
        pdf = PdfReader(pdf_path)
        names: list[str] = []
        for page in pdf.pages:
            if not getattr(page, "Annots", None):
                continue
            for annot in page.Annots:
                if getattr(annot, "Subtype", None) != "/Widget" or not getattr(annot, "T", None):
                    continue
                raw = decode_pdf_name(str(annot.T).strip("() /"))
                if raw and raw not in names:
                    names.append(raw)
        return {n: "string" for n in names}

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
            
    def fill_report(self, session: Session, user_input: str, schema_id: int, canonical_target: dict) -> dict[int, str]:
        """
        Extracts data using a canonical schema target, distributes the results
        to all associated templates, and fills them by name.
        """
        print(f"[1] Received report fill request for schema {schema_id}.")
        print("[2] Starting canonical extraction process...")
        
        try:
            # 1. Extract against the canonical target
            self.llm.set_model_config(provider="gemini", model_name="gemini-2.5-flash")
            self.llm._target_fields = canonical_target
            self.llm._transcript_text = user_input

            print("Canonization Process Begins")

            extraction_target = ReportSchemaProcessor.canonize(session=session, schema_id=schema_id)

            print("Canonization Process Complete")
            
            canonical_data = self.llm.extractor(extraction_target)
            
            
            print(f"[3] Canonical extraction complete. Distributing to templates...")
            
            # 2. Distribute to per-template dictionaries
            distribution = ReportSchemaProcessor.distribute(session, schema_id, canonical_data)
            
            # 3. Fill each template
            output_paths: dict[int, str] = {}
            
            for template_id, template_data in distribution.items():
                template = session.get(Template, template_id)
                if not template or not os.path.exists(template.pdf_path):
                     print(f"  -> Skipping template {template_id} (not found or missing PDF)")
                     continue
                     
                print(f"  -> Filling template {template_id} ({template.name})...")
                output_name = self.filler.fill_form_by_name(
                    pdf_form=template.pdf_path, 
                    field_values=template_data
                )
                output_paths[template_id] = output_name

            print("\n----------------------------------")
            print("✅ Report generation complete.")
            print(f"Outputs saved to: {list(output_paths.values())}")

            return output_paths

        except Exception as e:
            print(f"An error occurred during report generation: {e}")
            raise e
