from typing import List, Dict, Any

from src.file_manipulator import FileManipulator
from src.timeline_extractor import TimelineExtractor


class Controller:
    """
    Controller layer for FireForm.

    Responsible for orchestrating the processing pipeline:
    - Receiving user input
    - Extracting timeline information
    - Passing processed data to FileManipulator
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
        """
        Process the user input and fill the PDF form.

        Steps:
        1. Extract timeline events from the incident narrative
        2. Pass the original data to FileManipulator for form filling
        3. Attach timeline data to the result for downstream use
        """

        # Extract timeline from incident text
        timeline = self.timeline_extractor.extract_timeline(user_input)

        # Call existing FireForm pipeline
        result = self.file_manipulator.fill_form(
            user_input,
            fields,
            pdf_form_path
        )

        # Attach timeline to the result if possible
        if isinstance(result, dict):
            result["timeline"] = timeline

        return result

    def create_template(self, pdf_path: str) -> Dict[str, Any]:
        """
        Generate a template from the provided PDF form.
        """
        return self.file_manipulator.create_template(pdf_path)