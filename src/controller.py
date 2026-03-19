from typing import List, Dict, Any
from src.file_manipulator import FileManipulator
from src.timeline_extractor import TimelineExtractor
from src.incident_similarity import IncidentSimilarity

# Initialize globally (important)
similarity_engine = IncidentSimilarity()


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

        # 1. Extract timeline
        timeline = self.timeline_extractor.extract_timeline(user_input)

        # 2. Perform similarity search BEFORE adding new incident
        similar_cases = similarity_engine.search(user_input)

        # 3. Fill form
        result = self.file_manipulator.fill_form(
            user_input,
            fields,
            pdf_form_path
        )

        # 4. Store new incident AFTER search
        similarity_engine.add_incident(user_input)

        # 5. Attach results
        if isinstance(result, dict):
            result["timeline"] = timeline
            result["similar_incidents"] = similar_cases

        return result

    def create_template(self, pdf_path: str) -> Dict[str, Any]:
        return self.file_manipulator.create_template(pdf_path)