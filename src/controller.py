from src.file_manipulator import FileManipulator
from src.field_detector import PDFFieldDetector

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()
        self.field_detector = PDFFieldDetector()

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        return self.file_manipulator.fill_form(user_input, fields, pdf_form_path)
    
    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)

    def detect_fields(self, pdf_path: str):
        return self.field_detector.detect_fields(pdf_path)