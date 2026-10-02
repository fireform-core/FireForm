"""Tests for FormService that verify the template description reaches the controller."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models import Template
from app.services.form import FormService


def test_fill_and_persist_passes_template_description_to_controller():
    service = FormService()
    service.controller = MagicMock()
    service.controller.fill_form.return_value = "/tmp/filled.pdf"

    template = Template(
        id=1,
        name="Test Template",
        description="Wildfire incident communications plan",
        fields={},
        pdf_path="/tmp/template.pdf",
    )

    session = MagicMock()

    with patch(
        "app.services.form.create_form",
        side_effect=lambda session, submission: submission,
    ):
        result = service.fill_and_persist(
            session=session,
            template=template,
            transcript="Wildfire reported near Blackwood Canyon.",
            input_id=uuid4(),
            model="test-model",
        )

    service.controller.fill_form.assert_called_once_with(
        user_input="Wildfire reported near Blackwood Canyon.",
        fields={},
        pdf_form_path="/tmp/template.pdf",
        model="test-model",
        description="Wildfire incident communications plan",
    )

    assert result.output_pdf_path == "/tmp/filled.pdf"