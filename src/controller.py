from src.file_manipulator import FileManipulator

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()
    def validate_input(self, user_input: str) -> tuple:
        if not user_input or not user_input.strip():
            return False, "Input is empty"

        if len(user_input.strip()) < 10:
            return False, "Input too short. Please provide more details."

        return True, "Valid"
    
    def fill_form(self, user_input: str, fields: list, pdf_form_path: str) -> None | str:
    
    
        is_valid, message = self.validate_input(user_input)
    
        if not is_valid:
            raise ValueError(f"Invalid input: {message}")

        return self.file_manipulator.fill_form(user_input, fields, pdf_form_path)
    
    def prepare_fillable(self, pdf_path: str):
        return self.file_manipulator.prepare_fillable(pdf_path)