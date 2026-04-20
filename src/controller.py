from src.template_mapper import TemplateMapper
from src.validation import validate_extracted_data
from src.file_manipulator import FileManipulator

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()
        self.mapper = TemplateMapper({
        "patient_name": "NameField",
        "age": "AgeField",
        "diagnosis": "DiagnosisField"
})
    def map_data(self, validated_data: dict):
    return self.mapper.map_to_pdf_fields(validated_data)
    
    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
    data = self.file_manipulator.fill_form(user_input, fields, pdf_form_path)

    if not validate_extracted_data(data):
        raise ValueError("Invalid extracted data")

    return data
    
    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)
