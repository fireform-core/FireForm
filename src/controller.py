# controller.py 
from src.file_manipulator import FileManipulator

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()

        #timeline field added
    def fill_form(self, user_input: str, definitions: list, pdf_fields: list, pdf_form_path: str, use_timeline: bool = False):
        return self.file_manipulator.fill_form(
            user_input, definitions, pdf_fields, pdf_form_path, use_timeline
        )

    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)
