"""
tests/test_llm_checkpoint.py 
"""

import os
import sys
import unittest
import tempfile
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

class CheckpointTestCase(unittest.TestCase):
    """
    Base class that redirects STATE_DIR to a temp directory for each test
    so tests never write to /tmp/fireform_states or interfere with each other.
    """
 
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.patcher = patch.object(llm_module, "STATE_DIR", self.tmp_dir)
        self.patcher.start()
 
    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
 
    def make_llm(self, fields=None, transcript=None):
        inst = LLM()
        inst._transcript_text = transcript or TRANSCRIPT
        inst._target_fields = fields if fields is not None else FIELDS_LIST
        return inst

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


#checkpoint I/O tests 
class TestCheckpointIO(CheckpointTestCase):
 
    def test_save_creates_file(self):
        llm = self.make_llm()
        llm._setup_checkpoint()
        assert llm._state_file is not None
        llm._json = {"name": "Jane Smith"}
        llm.save_state()
        self.assertTrue(os.path.exists(llm._state_file))
 
    def test_load_restores_json(self):
        llm = self.make_llm()
        llm._setup_checkpoint()
        llm._json = {"name": "Jane Smith"}
        llm.save_state()
 
        fresh = self.make_llm()
        fresh._setup_checkpoint()
        resumed = fresh.load_state()
 
        self.assertTrue(resumed)
        self.assertEqual(fresh._json, {"name": "Jane Smith"})
 
    def test_load_returns_false_when_no_state_file(self):
        llm = self.make_llm()
        llm._setup_checkpoint()
        self.assertFalse(llm.load_state())
 
    def test_clear_removes_file(self):
        llm = self.make_llm()
        llm._setup_checkpoint()
        assert llm._state_file is not None
        llm._json = {"name": "Jane Smith"}
        llm.save_state()
        llm.clear_state()
        self.assertFalse(os.path.exists(llm._state_file))
 
    def test_load_handles_corrupt_file_gracefully(self):
        llm = self.make_llm()
        llm._setup_checkpoint()
        assert llm._state_file is not None
        with open(llm._state_file, "w") as f:
            f.write("{{ not valid JSON !!!")
        result = llm.load_state()
        self.assertFalse(result)
        self.assertEqual(llm._json, {})
 
    def test_save_is_atomic_no_tmp_file_left(self):
        """After save_state(), no .tmp file should remain."""
        llm = self.make_llm()
        llm._setup_checkpoint()
        llm._json = {"name": "Jane Smith"}
        llm.save_state()
        assert llm._state_file is not None
        self.assertFalse(os.path.exists(llm._state_file + ".tmp"))
        self.assertTrue(os.path.exists(llm._state_file))
 
    def test_save_before_setup_is_safe_noop(self):
        """save_state() before _setup_checkpoint() must not raise."""
        llm = LLM()
        try:
            llm.save_state()
        except Exception as e:
            self.fail(f"save_state() raised unexpectedly before setup: {e}")

if __name__ == "__main__":
    unittest.main()