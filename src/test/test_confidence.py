import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import pytest
from src.llm import LLM


@pytest.fixture
def llm():
    fields = {"name": None, "date": None, "location": None}
    return LLM(transcript_text="John went to Mumbai on 2024-01-15", target_fields=fields)


# --- _compute_field_confidence tests ---

def test_confidence_none_value(llm):
    assert llm._compute_field_confidence(None) == 0.0

def test_confidence_empty_string(llm):
    assert llm._compute_field_confidence("") == 0.0

def test_confidence_minus_one(llm):
    assert llm._compute_field_confidence("-1") == 0.0

def test_confidence_normal_string(llm):
    assert llm._compute_field_confidence("John Smith") >= 0.8

def test_confidence_vague_not_specified(llm):
    assert llm._compute_field_confidence("not specified") < 0.5

def test_confidence_vague_na(llm):
    assert llm._compute_field_confidence("N/A") < 0.5

def test_confidence_vague_unknown(llm):
    assert llm._compute_field_confidence("unknown") < 0.5

def test_confidence_short_string(llm):
    assert llm._compute_field_confidence("ab") < 0.5

def test_confidence_plural_list(llm):
    assert llm._compute_field_confidence(["val1", "val2"]) == 0.85

def test_confidence_empty_list(llm):
    assert llm._compute_field_confidence([]) == 0.0


# --- build_extraction_result tests ---

def test_requires_review_true_when_low_confidence(llm):
    llm._json = {"name": "John", "date": None, "location": "N/A"}
    result = llm.build_extraction_result()
    assert result["_meta"]["requires_review"] is True
    assert "date" in result["_meta"]["low_confidence_fields"]

def test_requires_review_false_when_all_confident(llm):
    llm._json = {"name": "John Smith", "date": "2024-01-15", "location": "Mumbai"}
    result = llm.build_extraction_result()
    assert result["_meta"]["requires_review"] is False
    assert result["_meta"]["low_confidence_fields"] == []

def test_overall_confidence_is_average(llm):
    llm._json = {"name": "Alice", "date": "2024-03-01"}
    result = llm.build_extraction_result()
    assert 0.0 <= result["_meta"]["overall_confidence"] <= 1.0

def test_each_field_has_value_and_confidence(llm):
    llm._json = {"name": "Bob"}
    result = llm.build_extraction_result()
    assert "value" in result["name"]
    assert "confidence" in result["name"]

def test_empty_json_returns_zero_confidence(llm):
    llm._json = {}
    result = llm.build_extraction_result()
    assert result["_meta"]["overall_confidence"] == 0.0
    assert result["_meta"]["requires_review"] is False