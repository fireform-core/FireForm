"""Tests for app.services.form_filler without Ollama.

Uses the real ICS 205A from the benchmark data: the template is built from the
PDF itself, the model call is patched, and the filled PDF is read back.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pypdf import PdfReader
from requests import HTTPError

from app.services.form_filler import filler, template
from app.services.form_filler.exceptions import ModelNotInstalledError

ICS_205A = str(Path(__file__).resolve().parents[1] / "benchmark/data/pdfs/ics_205a.pdf")
TABLE = "resource_summary_0_table"


def test_template_has_geometry_table_and_tooltip_descriptions():
    schema, tables, groups = template.create_template(ICS_205A)
    props = schema["properties"]

    # The 34-row contact list comes back as one array of rows
    assert props[TABLE]["type"] == "array"
    assert list(props[TABLE]["items"]["properties"]) == [
        "Incident_Assigned_Position",
        "Name_Alphabetized",
        "Method_s_of_Contact_phone_pager_cell_etc",
    ]
    assert tables[0]["row_count"] == 34
    assert groups["Name_Alphabetized"][0] == "Name AlphabetizedRow1"

    # Scalar fields keep their PDF names and use the /TU tooltip as description
    assert props["1 Incident Name_9"]["description"] == "Incident Name:"


def test_fill_maps_rows_back_to_widgets_and_writes_pdf(tmp_path):
    answer = {
        "1 Incident Name_9": "Blackwood Canyon Wildfire",
        TABLE: [
            {"Incident_Assigned_Position": "IC", "Name_Alphabetized": "Ana Diaz",
             "Method_s_of_Contact_phone_pager_cell_etc": "555-0101"},
            {"Incident_Assigned_Position": "Safety", "Name_Alphabetized": "Bo Chen",
             "Method_s_of_Contact_phone_pager_cell_etc": "555-0102"},
        ],
    }
    out_path = tmp_path / "filled.pdf"

    with patch.object(filler, "call_model", return_value=json.dumps(answer)) as call:
        result = filler.fill(ICS_205A, "Narrative text.", str(out_path), "test-model")

    prompt, schema, model = call.call_args.args
    assert "<incident_narrative>\nNarrative text.\n</incident_narrative>" in prompt
    assert prompt.startswith(filler.PROMPT.rstrip())
    assert model == "test-model"

    assert result["values"]["Name AlphabetizedRow2"] == "Bo Chen"

    fields = PdfReader(str(out_path)).get_fields()
    assert fields["1 Incident Name_9"]["/V"] == "Blackwood Canyon Wildfire"
    assert fields["Incident Assigned PositionRow1"]["/V"] == "IC"
    assert fields["Methods of Contact phone pager cell etcRow2"]["/V"] == "555-0102"
    assert fields["Name AlphabetizedRow3"].get("/V", "") == ""


def test_fill_defaults_to_configured_model():
    with patch.object(filler, "call_model", return_value="{}") as call:
        filler.fill(ICS_205A, "Narrative text.")

    assert call.call_args.args[2] == filler.OLLAMA_MODEL


def test_call_model_raises_for_uninstalled_model():
    with patch.object(filler.requests, "post") as post:
        response = post.return_value
        response.raise_for_status.side_effect = HTTPError(
            response=response,
        )
        response.status_code = 404

        with pytest.raises(ModelNotInstalledError, match="test-model"):
            filler.call_model("prompt", {"type": "object"}, "test-model")
