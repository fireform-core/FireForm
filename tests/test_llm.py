import json
from unittest.mock import patch, MagicMock
from src.llm import LLM


SAMPLE_TRANSCRIPT = (
    "Officer Voldemort here, at an incident reported at 456 Oak Street. "
    "Two victims, Mark Smith and Jane Doe. "
    "Handed off to Sheriff's Deputy Alvarez. End of transmission."
)

SAMPLE_FIELDS = {
    "reporting_officer": "string",
    "incident_location": "string",
    "victim_name_s": "string",
    "assisting_officer": "string",
}


def _make_mock_response(payload: dict) -> MagicMock:
    """Helper: build a mock requests.Response that returns payload as JSON."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": json.dumps(payload)}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# build_batch_prompt
# ---------------------------------------------------------------------------

def test_build_batch_prompt_contains_all_fields():
    llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
    prompt = llm.build_batch_prompt()

    for field in SAMPLE_FIELDS:
        assert field in prompt, f"Expected field '{field}' in batch prompt"

    assert SAMPLE_TRANSCRIPT in prompt


def test_build_batch_prompt_contains_transcript():
    llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
    prompt = llm.build_batch_prompt()
    assert SAMPLE_TRANSCRIPT in prompt


# ---------------------------------------------------------------------------
# main_loop_batch — happy path
# ---------------------------------------------------------------------------

def test_main_loop_batch_single_api_call():
    """main_loop_batch must call the Ollama API exactly once, regardless of field count."""
    llm_response = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": "456 Oak Street",
        "victim_name_s": ["Mark Smith", "Jane Doe"],
        "assisting_officer": "Deputy Alvarez",
    }

    with patch("requests.post", return_value=_make_mock_response(llm_response)) as mock_post:
        llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
        llm.main_loop_batch()

        assert mock_post.call_count == 1, (
            f"Expected exactly 1 API call, got {mock_post.call_count}. "
            "main_loop_batch should not loop per-field."
        )


def test_main_loop_batch_populates_all_fields():
    llm_response = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": "456 Oak Street",
        "victim_name_s": None,        # missing value
        "assisting_officer": "Deputy Alvarez",
    }

    with patch("requests.post", return_value=_make_mock_response(llm_response)):
        llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
        result = llm.main_loop_batch().get_data()

    assert result["reporting_officer"] == "Officer Voldemort"
    assert result["incident_location"] == "456 Oak Street"
    assert result["victim_name_s"] is None          # null maps to None
    assert result["assisting_officer"] == "Deputy Alvarez"


def test_main_loop_batch_handles_list_values():
    """Plural values returned as a JSON list should be joined into '; ' separated string."""
    llm_response = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": "456 Oak Street",
        "victim_name_s": ["Mark Smith", "Jane Doe"],
        "assisting_officer": "Deputy Alvarez",
    }

    with patch("requests.post", return_value=_make_mock_response(llm_response)):
        llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
        result = llm.main_loop_batch().get_data()

    assert result["victim_name_s"] == ["Mark Smith", "Jane Doe"]


# ---------------------------------------------------------------------------
# main_loop_batch — markdown code-fence stripping
# ---------------------------------------------------------------------------

def test_main_loop_batch_strips_markdown_fences():
    raw_with_fences = (
        "```json\n"
        + json.dumps({
            "reporting_officer": "Officer Voldemort",
            "incident_location": "456 Oak Street",
            "victim_name_s": None,
            "assisting_officer": "Deputy Alvarez",
        })
        + "\n```"
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": raw_with_fences}
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_resp):
        llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
        result = llm.main_loop_batch().get_data()

    assert result["reporting_officer"] == "Officer Voldemort"


# ---------------------------------------------------------------------------
# main_loop_batch — fallback to sequential main_loop on bad JSON
# ---------------------------------------------------------------------------

def test_main_loop_batch_falls_back_on_invalid_json():
    """If the LLM returns garbage instead of JSON, fall back to main_loop()."""
    bad_resp = MagicMock()
    bad_resp.json.return_value = {"response": "Sorry, I cannot help with that."}
    bad_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=bad_resp):
        with patch.object(LLM, "main_loop", return_value=MagicMock()) as mock_fallback:
            llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
            llm.main_loop_batch()
            mock_fallback.assert_called_once()


# ---------------------------------------------------------------------------
# main_loop_batch vs main_loop — call count comparison
# ---------------------------------------------------------------------------

def test_main_loop_batch_fewer_calls_than_main_loop():
    """
    Explicitly show that main_loop_batch makes 1 call while main_loop
    makes len(fields) calls — the core performance improvement.
    """
    n_fields = len(SAMPLE_FIELDS)
    llm_response = {k: "value" for k in SAMPLE_FIELDS}

    with patch("requests.post", return_value=_make_mock_response(llm_response)) as mock_post:
        llm = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
        llm.main_loop_batch()
        batch_calls = mock_post.call_count

    single_resp = MagicMock()
    single_resp.json.return_value = {"response": "some value"}
    single_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=single_resp) as mock_post:
        llm2 = LLM(transcript_text=SAMPLE_TRANSCRIPT, target_fields=SAMPLE_FIELDS)
        llm2.main_loop()
        sequential_calls = mock_post.call_count

    assert batch_calls == 1
    assert sequential_calls == n_fields
    assert batch_calls < sequential_calls
