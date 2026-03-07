from src.file_manipulator import FileManipulator

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()

    def extract_data(self, user_input: str, fields: dict, existing_data: dict = None):
        return self.file_manipulator.extract_data(user_input, fields, existing_data)

    def fill_pdf(self, answers: dict, pdf_form_path: str):
        return self.file_manipulator.fill_pdf(answers, pdf_form_path)
    
    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)