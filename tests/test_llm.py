"""Regression tests for prompt rendering without calling Ollama."""

from unittest.mock import mock_open, patch

import pytest

from app.services.llm import LLM


def test_build_prompt_uses_bundled_template():
    prompt = LLM(transcript_text="John Smith signed the form.").build_prompt(
        "Signature", "signature"
    )

    assert "Target JSON field to find in text: Signature" in prompt
    assert "Expected value type: signature" in prompt
    assert "TEXT: John Smith signed the form." in prompt


@pytest.mark.parametrize(
    "literal",
    [
        'EXAMPLE: {"value": "John Smith"}',
        'EXAMPLE: {"value": {"names": ["John", "Smith"]}}',
        "An unmatched opening brace: {",
        "An unmatched closing brace: }",
        "Unknown slots: {unknown} $unknown ${unknown}",
        "Literal dollars: $5 and a trailing $",
    ],
)
def test_build_prompt_preserves_literal_template_content(literal):
    template = "$field | $type | $text\n" + literal
    with patch("app.services.llm.open", mock_open(read_data=template)):
        prompt = LLM(transcript_text="John Smith").build_prompt(
            "Signature", "signature"
        )

    assert prompt == "Signature | signature | John Smith\n" + literal


def test_build_prompt_does_not_substitute_inside_values():
    field = "Name $type ${text} {field}"
    field_type = "string $text {type}"
    transcript = 'Received {"value": "$field"}, ${type}, and {text}.'
    with patch("app.services.llm.open", mock_open(read_data="$field | $type | $text")):
        prompt = LLM(transcript_text=transcript).build_prompt(field, field_type)

    assert prompt == f"{field} | {field_type} | {transcript}"


def test_build_prompt_defaults_to_string_type():
    with patch("app.services.llm.open", mock_open(read_data="$field | $type | $text")):
        prompt = LLM(transcript_text="John Smith").build_prompt("Name")

    assert prompt == "Name | string | John Smith"
