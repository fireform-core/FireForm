from src.external_apis_coordinator import ExternalAPIsCoordinator
from src.file_manipulator import FileManipulator

class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()
        self.external_apis_coordinator = ExternalAPIsCoordinator()

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        return self.file_manipulator.fill_form(user_input, fields, pdf_form_path)
    
    def create_template(self, pdf_path: str):
        return self.file_manipulator.create_template(pdf_path)

    def get_weather(self, latitude: float, longitude: float):
        return self.external_apis_coordinator.get_weather(latitude, longitude)