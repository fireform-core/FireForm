from typing import List, Dict, Any
from src.file_manipulator import FileManipulator
from src.timeline_extractor import TimelineExtractor


class Controller:
    """
    Controller layer for FireForm.
    Responsible for orchestrating the processing pipeline.
    """

    def __init__(self) -> None:
        self.file_manipulator = FileManipulator()
        self.timeline_extractor = TimelineExtractor()

    def fill_form(
        self,
        user_input: str,
        fields: List[str],
        pdf_form_path: str
    ) -> Dict[str, Any]:

        timeline = self.timeline_extractor.extract_timeline(user_input)

        result = self.file_manipulator.fill_form(
            user_input,
            fields,
            pdf_form_path
        )

        if isinstance(result, dict):
            result["timeline"] = timeline

        return result

    def create_template(self, pdf_path: str) -> Dict[str, Any]:
        return self.file_manipulator.create_template(pdf_path)