"""
Comprehensive tests for structured extraction functionality.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from src.llm import LLM
from src.utils.validation import requires_review


class TestStructuredExtraction:
    """Test structured extraction methods."""
    
    def test_extract_structured_basic(self):
        """Test basic structured extraction."""
        llm = LLM()
        llm._transcript_text = "John Doe works as Manager"
        llm._target_fields = ["name", "title"]
        
        with patch('requests.Session') as mock_session:
            mock_response = Mock()
            mock_response.text = '{"name": "John Doe", "title": "Manager"}'
            mock_response.json.return_value = {
                "response": '{"name": "John Doe", "title": "Manager"}'
            }
            mock_response.headers.get.return_value = None
            mock_response.raise_for_status = Mock()
            
            mock_session_instance = Mock()
            mock_session_instance.post.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            result = llm.extract_structured()
            assert result == '{"name": "John Doe", "title": "Manager"}'
    
    def test_extract_structured_safe_success(self):
        """Test safe extraction with valid JSON."""
        llm = LLM()
        llm._transcript_text = "John Doe works as Manager"
        llm._target_fields = ["name", "title"]
        
        with patch.object(llm, 'extract_structured') as mock_extract:
            mock_extract.return_value = '{"name": "John Doe", "title": "Manager"}'
            
            success = llm.extract_structured_safe()
            assert success is True
            assert llm.get_data() == {"name": "John Doe", "title": "Manager"}

    
    def test_extract_structured_safe_with_markdown(self):
        """Test extraction with markdown code blocks."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["field1"]
        
        with patch.object(llm, 'extract_structured') as mock_extract:
            mock_extract.return_value = '```json\n{"field1": "value1"}\n```'
            
            success = llm.extract_structured_safe()
            assert success is True
            assert llm.get_data() == {"field1": "value1"}
    
    def test_extract_structured_safe_missing_fields(self):
        """Test extraction with missing fields."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["field1", "field2"]
        
        with patch.object(llm, 'extract_structured') as mock_extract:
            mock_extract.return_value = '{"field1": "value1"}'
            
            success = llm.extract_structured_safe()
            assert success is True
            data = llm.get_data()
            assert data["field1"] == "value1"
            assert data["field2"] == "-1"  # Missing field gets default
    
    def test_extract_structured_safe_invalid_json(self):
        """Test extraction with invalid JSON."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["field1"]
        
        with patch.object(llm, 'extract_structured') as mock_extract:
            mock_extract.return_value = 'not valid json'
            
            success = llm.extract_structured_safe()
            assert success is False

    
    def test_extract_structured_safe_empty_response(self):
        """Test extraction with empty response."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["field1"]
        
        with patch.object(llm, 'extract_structured') as mock_extract:
            mock_extract.return_value = ''
            
            success = llm.extract_structured_safe()
            assert success is False
    
    def test_extract_structured_safe_list_values(self):
        """Test extraction with list values."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["names"]
        
        with patch.object(llm, 'extract_structured') as mock_extract:
            mock_extract.return_value = '{"names": ["John", "Jane"]}'
            
            success = llm.extract_structured_safe()
            assert success is True
            assert llm.get_data() == {"names": ["John", "Jane"]}


class TestValidation:
    """Test validation utilities."""
    
    def test_requires_review_empty_data(self):
        """Test review required for empty data."""
        assert requires_review({}, ["field1"]) is True
    
    def test_requires_review_missing_field(self):
        """Test review required for missing field."""
        assert requires_review({"field1": "value"}, ["field1", "field2"]) is True
    
    def test_requires_review_default_value(self):
        """Test review required for default value."""
        assert requires_review({"field1": "-1"}, ["field1"]) is True
    
    def test_requires_review_empty_string(self):
        """Test review required for empty string."""
        assert requires_review({"field1": ""}, ["field1"]) is True

    
    def test_requires_review_valid_data(self):
        """Test no review needed for valid data."""
        assert requires_review({"field1": "value"}, ["field1"]) is False
    
    def test_requires_review_empty_list(self):
        """Test review required for empty list."""
        assert requires_review({"field1": []}, ["field1"]) is True
    
    def test_requires_review_list_with_defaults(self):
        """Test review required for list with only defaults."""
        assert requires_review({"field1": ["-1", ""]}, ["field1"]) is True
    
    def test_requires_review_valid_list(self):
        """Test no review needed for valid list."""
        assert requires_review({"field1": ["value1", "value2"]}, ["field1"]) is False
    
    def test_requires_review_invalid_input(self):
        """Test review required for invalid input types."""
        assert requires_review(None, ["field1"]) is True
        assert requires_review("not a dict", ["field1"]) is True
    
    def test_requires_review_no_required_fields(self):
        """Test no review needed when no fields required."""
        assert requires_review({"field1": "value"}, []) is False


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_extract_structured_too_many_fields(self):
        """Test extraction with too many fields."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = [f"field{i}" for i in range(30)]
        
        with patch('requests.Session') as mock_session:
            mock_response = Mock()
            mock_response.text = '{}'
            mock_response.json.return_value = {"response": '{}'}
            mock_response.headers.get.return_value = None
            mock_response.raise_for_status = Mock()
            
            mock_session_instance = Mock()
            mock_session_instance.post.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            # Should limit to 20 fields
            result = llm.extract_structured()
            assert result is not None
            
            # Verify the prompt was called with only 20 fields
            mock_session_instance.post.assert_called_once()
            call_args = mock_session_instance.post.call_args
            
            # Extract the payload from the call
            payload = call_args[1]['json']  # kwargs['json']
            prompt = payload['prompt']
            
            # Verify only first 20 fields are in the prompt
            expected_fields = [f"field{i}" for i in range(20)]
            for field in expected_fields:
                assert field in prompt, f"Expected field {field} not in prompt"
            
            # Verify fields 20-29 are NOT in the prompt
            for i in range(20, 30):
                assert f"field{i}" not in prompt, f"Field field{i} should not be in prompt (limit is 20)"

    
    def test_extract_structured_response_too_large(self):
        """Test extraction with oversized response."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["field1"]
        
        with patch('requests.Session') as mock_session:
            mock_response = Mock()
            mock_response.text = 'x' * (2 * 1024 * 1024)  # 2MB
            mock_response.headers.get.return_value = str(2 * 1024 * 1024)
            
            mock_session_instance = Mock()
            mock_session_instance.post.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            with pytest.raises(ValueError, match="Response too large"):
                llm.extract_structured()
    
    def test_extract_structured_connection_error(self):
        """Test extraction with connection error."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["field1"]
        
        with patch('requests.Session') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.post.side_effect = Exception("Connection failed")
            mock_session.return_value = mock_session_instance
            
            with pytest.raises(RuntimeError):
                llm.extract_structured()
    
    def test_extract_structured_safe_sanitization(self):
        """Test that extracted values are sanitized."""
        llm = LLM()
        llm._transcript_text = "Test"
        llm._target_fields = ["field1"]
        
        with patch.object(llm, 'extract_structured') as mock_extract:
            # Include potentially dangerous content
            mock_extract.return_value = '{"field1": "<script>alert(1)</script>"}'
            
            success = llm.extract_structured_safe()
            assert success is True
            # Should be sanitized (HTML tags removed)
            assert "<script>" not in llm.get_data()["field1"]
