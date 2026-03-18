import pytest
from api.main import app
from unittest.mock import MagicMock
from src.controller import Controller


class TestControllerTimeline:
    """
    Test suite for verifying timeline extraction integration
    within the FireForm controller pipeline.
    """

    @pytest.fixture
    def controller(self):
        """
        Provides a Controller instance with mocked FileManipulator.
        """
        controller = Controller()
        controller.file_manipulator = MagicMock()

        # Simulate file_manipulator returning a valid result dict
        controller.file_manipulator.fill_form.return_value = {
            "status": "success",
            "filled_pdf": "output.pdf"
        }

        return controller

    def test_timeline_extraction_integration(self, controller):
        """
        Ensure timeline data is added to controller output.
        """

        incident_text = (
            "Engine 12 arrived at 3:10 PM. "
            "Fire contained at 3:25 PM."
        )

        result = controller.fill_form(
            user_input=incident_text,
            fields=[],
            pdf_form_path="dummy.pdf"
        )

        assert isinstance(result, dict)
        assert "timeline" in result
        assert len(result["timeline"]) == 2
        assert result["timeline"][0]["time"] == "15:10"
        assert result["timeline"][1]["time"] == "15:25"

    def test_no_timeline_when_no_times(self, controller):
        """
        Ensure timeline is empty when no timestamps exist.
        """

        incident_text = "Firefighters responded quickly to the incident."

        result = controller.fill_form(
            user_input=incident_text,
            fields=[],
            pdf_form_path="dummy.pdf"
        )

        assert "timeline" in result
        assert result["timeline"] == []

    def test_controller_pipeline_still_calls_file_manipulator(self, controller):
        """
        Ensure existing pipeline behavior is preserved.
        """

        incident_text = "Engine arrived at 3:10 PM."

        controller.fill_form(
            user_input=incident_text,
            fields=["name", "location"],
            pdf_form_path="incident_form.pdf"
        )

        controller.file_manipulator.fill_form.assert_called_once()

    def test_invalid_input_handling(self, controller):
        """
        Ensure controller handles invalid input gracefully.
        """

        result = controller.fill_form(
            user_input="",
            fields=[],
            pdf_form_path="dummy.pdf"
        )

        assert isinstance(result, dict)
        assert "timeline" in result