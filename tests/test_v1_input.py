"""Tests for POST /api/v1/input/text and GET /api/v1/input/{input_id}.

Uses the shared in-memory SQLite engine from conftest.py.  No Ollama or
Whisper involvement — text input is fully synchronous.
"""


TEXT_URL = "/api/v1/input/text"
INPUT_URL = "/api/v1/input"

# Narrative that passes all validation: > 20 chars, >= 10 words, << 50,000 chars.
VALID_NARRATIVE = (
    "Responded to a wildfire at Bear Creek Trailhead around 1:45 PM on July 10th. "
    "Lightning strike ignited timber litter in mixed conifer and chaparral."
)


# ---------------------------------------------------------------------------
# POST /api/v1/input/text
# ---------------------------------------------------------------------------

class TestSubmitTextInput:

    def test_201_returns_required_fields(self, client):
        resp = client.post(TEXT_URL, json={"narrative": VALID_NARRATIVE})
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "ready"
        assert body["input_type"] == "text"
        assert "input_id" in body
        assert "created_at" in body

    def test_201_character_and_word_counts_match_narrative(self, client):
        resp = client.post(TEXT_URL, json={"narrative": VALID_NARRATIVE})
        assert resp.status_code == 201
        body = resp.json()
        assert body["character_count"] == len(VALID_NARRATIVE)
        assert body["word_count"] == len(VALID_NARRATIVE.split())

    def test_201_optional_fields_accepted_and_visible_via_get(self, client):
        resp = client.post(TEXT_URL, json={
            "narrative": VALID_NARRATIVE,
            "station_id": "STA-045",
            "responder_badge": "FD-7842",
            "incident_date_hint": "2024-07-10",
        })
        assert resp.status_code == 201
        input_id = resp.json()["input_id"]

        get_resp = client.get(f"{INPUT_URL}/{input_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["station_id"] == "STA-045"
        assert body["responder_badge"] == "FD-7842"
        assert body["incident_date_hint"] == "2024-07-10"

    def test_narrative_stored_in_transcript_field(self, client):
        resp = client.post(TEXT_URL, json={"narrative": VALID_NARRATIVE})
        input_id = resp.json()["input_id"]
        get_resp = client.get(f"{INPUT_URL}/{input_id}")
        assert get_resp.json()["transcript"] == VALID_NARRATIVE

    def test_413_narrative_over_50000_chars(self, client):
        too_long = "x" * 50_001
        resp = client.post(TEXT_URL, json={"narrative": too_long})
        assert resp.status_code == 413
        body = resp.json()
        assert body["error_code"] == "NARRATIVE_TOO_LONG"
        assert body["detail"]["max_characters"] == 50_000
        assert body["detail"]["received_characters"] == 50_001

    def test_413_boundary_exactly_50000_chars_is_accepted(self, client):
        # Exactly at the limit: should succeed (> 50_000 is rejected, not >=).
        # Build a narrative at exactly 50,000 chars that has >= 10 words.
        phrase = "fire incident response "  # 23 chars
        narrative = (phrase * 2175)[:50_000]  # 2175*23=50025, sliced to 50000
        resp = client.post(TEXT_URL, json={"narrative": narrative})
        assert resp.status_code == 201

    def test_422_fewer_than_10_words_matches_request_validation_shape(self, client):
        # >= 20 chars so Pydantic minLength passes, but only 6 words.
        short = "Fire happened at the scene today here"  # 7 words, > 20 chars
        resp = client.post(TEXT_URL, json={"narrative": short})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["message"] == "Request validation failed"
        errs = body["validation_errors"]
        assert len(errs) == 1
        assert errs[0]["field"] == "narrative"
        assert errs[0]["issue"] == "Must contain at least 10 words"
        assert errs[0]["value"] == short

    def test_422_narrative_under_20_chars_triggers_pydantic_validation(self, client):
        resp = client.post(TEXT_URL, json={"narrative": "Too short"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert "validation_errors" in body

    def test_422_missing_narrative_field(self, client):
        resp = client.post(TEXT_URL, json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"

    def test_422_empty_string_narrative(self, client):
        resp = client.post(TEXT_URL, json={"narrative": ""})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# GET /api/v1/input/{input_id}
# ---------------------------------------------------------------------------

class TestGetInput:

    def _create(self, client, **kwargs):
        payload = {"narrative": VALID_NARRATIVE, **kwargs}
        resp = client.post(TEXT_URL, json=payload)
        assert resp.status_code == 201
        return resp.json()["input_id"]

    def test_200_returns_full_record(self, client):
        input_id = self._create(client)
        resp = client.get(f"{INPUT_URL}/{input_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["input_id"] == input_id
        assert body["input_type"] == "text"
        assert body["status"] == "ready"
        assert body["transcript"] == VALID_NARRATIVE
        assert body["character_count"] == len(VALID_NARRATIVE)
        assert body["word_count"] == len(VALID_NARRATIVE.split())
        assert body["created_at"] is not None
        assert body["updated_at"] is not None

    def test_200_voice_only_fields_are_null_for_text_input(self, client):
        input_id = self._create(client)
        body = client.get(f"{INPUT_URL}/{input_id}").json()
        assert body["original_filename"] is None
        assert body["audio_duration_seconds"] is None
        assert body["error_detail"] is None

    def test_200_retry_after_is_null_for_ready_input(self, client):
        input_id = self._create(client)
        body = client.get(f"{INPUT_URL}/{input_id}").json()
        assert body.get("retry_after_seconds") is None

    def test_404_unknown_uuid_returns_app_error_envelope(self, client):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"{INPUT_URL}/{fake_id}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error_code"] == "INPUT_NOT_FOUND"
        assert fake_id in body["message"]

    def test_404_message_contains_the_requested_id(self, client):
        target = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        resp = client.get(f"{INPUT_URL}/{target}")
        assert resp.status_code == 404
        assert target in resp.json()["message"]
