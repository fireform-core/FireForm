from src.file_manipulator import FileManipulator

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()

    def fill_form(
        self,
        user_input: str,
        fields: dict,
        pdf_form_path: str,
        retry_input_texts: list[str] | None = None,
        max_retry_rounds: int = 1,
    ):
        return self.file_manipulator.fill_form(
            user_input=user_input,
            fields=fields,
            pdf_form_path=pdf_form_path,
            retry_input_texts=retry_input_texts,
            max_retry_rounds=max_retry_rounds,
        )
    
    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)