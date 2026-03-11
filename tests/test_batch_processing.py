"""
Tests for Batch Processing Optimization
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.llm import LLM
import json


class TestBatchProcessing:
    """Test suite for O(1) batch processing functionality"""
    
    def test_batch_prompt_generation(self):
        """Test that batch prompt is generated correctly"""
        llm = LLM(
            transcript_text="Officer Smith, badge 4421, at Main Street",
            target_fields=["Officer Name", "Badge Number", "Location"],
            use_batch_processing=True
        )
        
        prompt = llm.build_batch_prompt(["Officer Name", "Badge Number", "Location"])
        
        assert "Officer Name" in prompt
        assert "Badge Number" in prompt
        assert "Location" in prompt
        assert "JSON" in prompt or "json" in prompt
        assert llm._transcript_text in prompt
    
    def test_batch_prompt_with_profile_labels(self):
        """Test batch prompt generation with profile labels enabled"""
        llm = LLM(
            transcript_text="Officer Smith responding to fire",
            target_fields={"Officer Name": "textbox_0_0", "Incident Type": "textbox_0_1"},
            use_profile_labels=True,
            use_batch_processing=True
        )
        
        prompt = llm.build_batch_prompt(["Officer Name", "Incident Type"])
        
        assert "Officer Name" in prompt
        assert "Incident Type" in prompt
        assert "TRANSCRIPT" in prompt or "transcript" in prompt.lower()
    
    @patch('src.llm.requests.post')
    def test_batch_processing_success(self, mock_post):
        """Test successful batch processing with valid JSON response"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "Officer Name": "Smith",
                "Badge Number": "4421",
                "Location": "Main Street"
            })
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        llm = LLM(
            transcript_text="Officer Smith, badge 4421, at Main Street",
            target_fields=["Officer Name", "Badge Number", "Location"],
            use_batch_processing=True
        )
        
        result = llm.main_loop()
        
        assert result._json["Officer Name"] == "Smith"
        assert result._json["Badge Number"] == "4421"
        assert result._json["Location"] == "Main Street"
        assert mock_post.call_count == 1  # Only one API call
    
    @patch('src.llm.requests.post')
    def test_batch_processing_with_markdown(self, mock_post):
        """Test batch processing handles markdown code blocks"""
        # Mock response with markdown formatting
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": '```json\n{"Officer Name": "Smith", "Badge Number": "4421"}\n```'
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        llm = LLM(
            transcript_text="Officer Smith, badge 4421",
            target_fields=["Officer Name", "Badge Number"],
            use_batch_processing=True
        )
        
        result = llm.main_loop()
        
        assert result._json["Officer Name"] == "Smith"
        assert result._json["Badge Number"] == "4421"
    
    @patch('src.llm.requests.post')
    def test_batch_processing_missing_fields(self, mock_post):
        """Test batch processing handles missing fields"""
        # Mock response with only some fields
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "Officer Name": "Smith"
                # Badge Number missing
            })
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        llm = LLM(
            transcript_text="Officer Smith",
            target_fields=["Officer Name", "Badge Number"],
            use_batch_processing=True
        )
        
        result = llm.main_loop()
        
        assert result._json["Officer Name"] == "Smith"
        assert result._json["Badge Number"] == "-1"  # Missing field defaults to -1
    
    @patch('src.llm.requests.post')
    def test_batch_processing_fallback_on_json_error(self, mock_post):
        """Test fallback to sequential processing on JSON parse error"""
        # First call returns invalid JSON (batch fails)
        # Subsequent calls return valid responses (sequential succeeds)
        responses = [
            Mock(json=lambda: {"response": "Invalid JSON {{{"}),  # Batch fails
            Mock(json=lambda: {"response": "Smith"}),  # Sequential call 1
            Mock(json=lambda: {"response": "4421"}),   # Sequential call 2
        ]
        
        for r in responses:
            r.raise_for_status = Mock()
        
        mock_post.side_effect = responses
        
        llm = LLM(
            transcript_text="Officer Smith, badge 4421",
            target_fields=["Officer Name", "Badge Number"],
            use_batch_processing=True
        )
        
        result = llm.main_loop()
        
        # Should have fallen back to sequential (3 calls total: 1 batch + 2 sequential)
        assert mock_post.call_count == 3
        assert result._json["Officer Name"] == "Smith"
        assert result._json["Badge Number"] == "4421"
    
    @patch('src.llm.requests.post')
    def test_sequential_processing_mode(self, mock_post):
        """Test sequential processing when explicitly disabled"""
        # Mock responses for each field
        responses = [
            Mock(json=lambda: {"response": "Smith"}),
            Mock(json=lambda: {"response": "4421"}),
            Mock(json=lambda: {"response": "Main Street"}),
        ]
        
        for r in responses:
            r.raise_for_status = Mock()
        
        mock_post.side_effect = responses
        
        llm = LLM(
            transcript_text="Officer Smith, badge 4421, at Main Street",
            target_fields=["Officer Name", "Badge Number", "Location"],
            use_batch_processing=False  # Explicitly disable
        )
        
        result = llm.main_loop()
        
        # Should make 3 separate calls (one per field)
        assert mock_post.call_count == 3
        assert result._json["Officer Name"] == "Smith"
        assert result._json["Badge Number"] == "4421"
        assert result._json["Location"] == "Main Street"
    
    def test_batch_processing_default_enabled(self):
        """Test that batch processing is enabled by default"""
        llm = LLM(
            transcript_text="Test",
            target_fields=["Field1"]
        )
        
        assert llm._use_batch_processing is True
    
    @patch('src.llm.requests.post')
    def test_batch_processing_with_dict_fields(self, mock_post):
        """Test batch processing works with dict-style fields"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "Officer Name": "Smith",
                "Badge Number": "4421"
            })
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        llm = LLM(
            transcript_text="Officer Smith, badge 4421",
            target_fields={"Officer Name": "textbox_0_0", "Badge Number": "textbox_0_1"},
            use_batch_processing=True
        )
        
        result = llm.main_loop()
        
        assert result._json["Officer Name"] == "Smith"
        assert result._json["Badge Number"] == "4421"
        assert mock_post.call_count == 1
    
    @patch('src.llm.requests.post')
    def test_batch_processing_connection_error(self, mock_post):
        """Test batch processing handles connection errors"""
        mock_post.side_effect = ConnectionError("Connection failed")
        
        llm = LLM(
            transcript_text="Test",
            target_fields=["Field1"],
            use_batch_processing=True
        )
        
        with pytest.raises(ConnectionError):
            llm.main_loop()
    
    @patch('src.llm.requests.post')
    def test_batch_processing_plural_values(self, mock_post):
        """Test batch processing handles plural values with semicolons"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "Victim Names": "John Doe; Jane Smith",
                "Officer Name": "Officer Brown"
            })
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        llm = LLM(
            transcript_text="Victims John Doe and Jane Smith, Officer Brown responding",
            target_fields=["Victim Names", "Officer Name"],
            use_batch_processing=True
        )
        
        result = llm.main_loop()
        
        # Plural values should be parsed into a list
        assert isinstance(result._json["Victim Names"], list)
        assert "John Doe" in result._json["Victim Names"]
        assert result._json["Officer Name"] == "Officer Brown"


class TestBatchProcessingPerformance:
    """Performance-related tests for batch processing"""
    
    @patch('src.llm.requests.post')
    def test_batch_reduces_api_calls(self, mock_post):
        """Test that batch processing reduces API calls from N to 1"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": json.dumps({
                f"Field{i}": f"Value{i}" for i in range(20)
            })
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        fields = [f"Field{i}" for i in range(20)]
        
        # Batch processing
        llm_batch = LLM(
            transcript_text="Test data",
            target_fields=fields,
            use_batch_processing=True
        )
        llm_batch.main_loop()
        
        # Should only make 1 API call for 20 fields
        assert mock_post.call_count == 1
    
    @patch('src.llm.requests.post')
    def test_sequential_makes_n_calls(self, mock_post):
        """Test that sequential processing makes N API calls"""
        mock_response = Mock()
        mock_response.json.return_value = {"response": "Value"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        fields = [f"Field{i}" for i in range(10)]
        
        # Sequential processing
        llm_seq = LLM(
            transcript_text="Test data",
            target_fields=fields,
            use_batch_processing=False
        )
        llm_seq.main_loop()
        
        # Should make 10 API calls for 10 fields
        assert mock_post.call_count == 10
