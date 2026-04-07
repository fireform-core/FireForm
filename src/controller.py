from src.file_manipulator import FileManipulator
from sqlmodel import Session
from src.report_schema import ReportSchemaProcessor

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        return self.file_manipulator.fill_form(user_input, fields, pdf_form_path)
    
    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)

    def extract_template_fields(self, pdf_path: str) -> dict[str, str]:
        return self.file_manipulator.extract_template_field_map(pdf_path)

    def fill_report(self, session: Session, user_input: str, schema_id: int) -> dict[int, str]:
        """
        Main pipeline entry point for filling a multi-template report schema.
        1. Triggers canonization to get the latest schema definition.
        2. Builds the JSON Schema extraction target for the LLM.
        3. Hands off to FileManipulator for actual processing.
        """
        canonical_schema = ReportSchemaProcessor.canonize(session, schema_id)
        extraction_target = ReportSchemaProcessor.build_extraction_target(canonical_schema)
        
        return self.file_manipulator.fill_report(
            session=session,
            user_input=user_input, 
            schema_id=schema_id,
            canonical_target=extraction_target
        )