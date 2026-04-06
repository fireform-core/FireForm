"""
tests/test_llm_checkpoint.py 
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import llm as llm_module
from llm import LLM


#helpers
TRANSCRIPT = (
    "The employee name is John Smith. "
    "The date is March 1. "
    "The location is Fire Station HQ."
)
FIELDS_LIST = ["name", "date", "location"]
FIELDS_DICT = {"name": None, "date": None, "location": None}


#session id tests
class TestSessionId(unittest.TestCase):
    """Session ID must be deterministic and must not collide across templates."""

    def test_same_inputs_produce_same_session_id(self):
        a = LLM()
        a._transcript_text = TRANSCRIPT
        a._target_fields = FIELDS_LIST
        a._setup_checkpoint()

        b = LLM()
        b._transcript_text = TRANSCRIPT
        b._target_fields = FIELDS_LIST
        b._setup_checkpoint()

        self.assertEqual(a._session_id, b._session_id)

    def test_different_transcript_produces_different_id(self):
        a = LLM()
        a._transcript_text = "Hello world"
        a._target_fields = FIELDS_LIST
        a._setup_checkpoint()

        b = LLM()
        b._transcript_text = "Different text"
        b._target_fields = FIELDS_LIST
        b._setup_checkpoint()

        self.assertNotEqual(a._session_id, b._session_id)

    def test_different_fields_produce_different_id(self):
        """Same transcript, different form templates must not share a session_id."""
        a = LLM()
        a._transcript_text = TRANSCRIPT
        a._target_fields = ["name", "date"]
        a._setup_checkpoint()

        b = LLM()
        b._transcript_text = TRANSCRIPT
        b._target_fields = ["unit", "location"]
        b._setup_checkpoint()

        self.assertNotEqual(a._session_id, b._session_id)

    def test_field_order_does_not_matter(self):
        """Field list order must not change the session_id (we sort before hashing)."""
        a = LLM()
        a._transcript_text = TRANSCRIPT
        a._target_fields = ["a", "b", "c"]
        a._setup_checkpoint()

        b = LLM()
        b._transcript_text = TRANSCRIPT
        b._target_fields = ["c", "a", "b"]
        b._setup_checkpoint()

        self.assertEqual(a._session_id, b._session_id)

    def test_dict_fields_same_as_list_fields(self):
        """Dict and list with the same keys must produce the same session_id."""
        a = LLM()
        a._transcript_text = TRANSCRIPT
        a._target_fields = FIELDS_LIST
        a._setup_checkpoint()

        b = LLM()
        b._transcript_text = TRANSCRIPT
        b._target_fields = FIELDS_DICT
        b._setup_checkpoint()

        self.assertEqual(a._session_id, b._session_id)


#get field name tests
class TestGetFieldNames(unittest.TestCase):
    """_get_field_names() must handle None, dict, and list correctly."""

    def test_none_returns_empty_list(self):
        inst = LLM()
        inst._target_fields = None
        self.assertEqual(inst._get_field_names(), [])

    def test_list_returned_as_is(self):
        inst = LLM()
        inst._target_fields = ["a", "b"]
        self.assertEqual(inst._get_field_names(), ["a", "b"])

    def test_dict_returns_keys(self):
        inst = LLM()
        inst._target_fields = {"name": None, "date": "March 1"}
        self.assertCountEqual(inst._get_field_names(), ["name", "date"])

    def test_empty_list(self):
        inst = LLM()
        inst._target_fields = []
        self.assertEqual(inst._get_field_names(), [])

    def test_empty_dict(self):
        inst = LLM()
        inst._target_fields = {}
        self.assertEqual(inst._get_field_names(), [])


if __name__ == "__main__":
    unittest.main()