from src.file_manipulator import FileManipulator

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str, use_batch_processing: bool = True):
        return self.file_manipulator.fill_form(user_input, fields, pdf_form_path, use_batch_processing)
    
    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)