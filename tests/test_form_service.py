"""Tests for FormService that verify the template description reaches the filler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models import Template
from app.services.form import FormService


def test_fill_and_persist_passes_template_description_to_filler(tmp_path):
    service = FormService()

    pdf_path = tmp_path / "template.pdf"
    pdf_path.touch()
    relative_pdf_path = "template.pdf"

    template = Template(
        id=1,
        name="Test Template",
        description="Wildfire incident communications plan",
        fields={},
        pdf_path=relative_pdf_path,
    )

    session = MagicMock()
    input_id = uuid4()

    with (
        patch("app.services.form.filler.fill") as fill,
        patch(
            "app.services.form.create_form",
            side_effect=lambda session, submission: submission,
        ),
        patch("app.services.form.paths.PROJECT_ROOT", tmp_path),
    ):
        result = service.fill_and_persist(
            session=session,
            template=template,
            transcript="Wildfire reported near Blackwood Canyon.",
            input_id=input_id,
            model="test-model",
        )

    fill.assert_called_once()
    call_kwargs = fill.call_args.kwargs

    assert call_kwargs["pdf_path"] == str(pdf_path.resolve())
    assert call_kwargs["narrative"] == "Wildfire reported near Blackwood Canyon."
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["description"] == "Wildfire incident communications plan"
    assert call_kwargs["out_path"].endswith("_filled.pdf")

    assert result.template_id == 1
    assert result.input_id == input_id
    assert result.input_text == "Wildfire reported near Blackwood Canyon."
    assert result.output_pdf_path.endswith("_filled.pdf")
