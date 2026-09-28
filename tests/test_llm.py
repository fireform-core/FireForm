"""Unit tests for app.services.llm.LLM.add_response_to_json.

Covers #334: calling add_response_to_json twice for the same field used to
raise `AttributeError: 'str' object has no attribute 'append'`, because the
first call stores a plain string/None and the second call unconditionally
tries to .append() to it.
"""

from app.services.llm import LLM


def test_single_value_stored_directly():
    llm = LLM()
    llm.add_response_to_json("name", "John")
    assert llm.get_data() == {"name": "John"}


def test_repeated_field_upgrades_to_list_without_crashing():
    llm = LLM()
    llm.add_response_to_json("name", "John")
    llm.add_response_to_json("name", "Mike")

    assert llm.get_data() == {"name": ["John", "Mike"]}


def test_third_occurrence_appends_to_existing_list():
    llm = LLM()
    llm.add_response_to_json("name", "John")
    llm.add_response_to_json("name", "Mike")
    llm.add_response_to_json("name", "Alex")

    assert llm.get_data() == {"name": ["John", "Mike", "Alex"]}


def test_sentinel_value_is_stored_as_none():
    """The LLM returns the literal string "-1" as a sentinel for "no answer"."""
    llm = LLM()
    llm.add_response_to_json("phone", "-1")
    assert llm.get_data() == {"phone": None}


def test_value_is_stripped_and_unquoted():
    llm = LLM()
    llm.add_response_to_json("city", '  "Hyderabad"  ')
    assert llm.get_data() == {"city": "Hyderabad"}
