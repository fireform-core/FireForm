from unittest.mock import mock_open, patch

from app.services.llm import LLM


def test_build_prompt_preserves_literal_braces():
    template = """
Field: {field}
Type: {type}
Text: {text}

Example JSON:
{"name": "John Doe"}
"""

    with patch("builtins.open", mock_open(read_data=template)):
        llm = LLM(transcript_text="John Doe")

        result = llm.build_prompt(
            current_field="name",
            current_type="string",
        )

    assert "Field: name" in result
    assert "Type: string" in result
    assert "Text: John Doe" in result
    assert '{"name": "John Doe"}' in result