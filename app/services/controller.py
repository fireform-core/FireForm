from app.services.external_apis_coordinator import ExternalAPIsCoordinator
from app.services.file_manipulator import FileManipulator


class Controller:
    def __init__(self):
        self.file_manipulator = FileManipulator()
        self.external_apis_coordinator = ExternalAPIsCoordinator()

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str, model: str | None = None):
        return self.file_manipulator.fill_form(user_input, fields, pdf_form_path, model=model)
    
    def prepare_fillable(self, pdf_path: str):
        return self.file_manipulator.prepare_fillable(pdf_path)

    def get_weather(self, latitude: float, longitude: float, start_date: str, end_date: str, hourly_fields: list = None):
        return self.external_apis_coordinator.get_weather(latitude, longitude, start_date, end_date, hourly_fields)

    def lookup_address(self, address: str) -> list[dict]:
        return self.external_apis_coordinator.lookup_address(address)