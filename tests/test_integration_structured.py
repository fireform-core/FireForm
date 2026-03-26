"""
Integration tests for structured extraction end-to-end flow.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.controller import Controller
from src.file_manipulator import FileManipulator
from src.llm import LLM


class TestIntegrationStructured:
    """Integration tests for the complete structured extraction flow."""
    
    @patch('src.file_manipulator.Filler')
    @patch('src.llm.requests.Session')
    @patch('pathlib.Path')
    @patch('os.access')
    @patch('os.path.getsize')
    def test_full_flow_structured_success(
        self, mock_getsize, mock_access, mock_path, mock_session, mock_filler
    ):
        """Test complete flow with successful structured extraction."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = True
        mock_path_obj.resolve.return_value = mock_path_obj
        mock_path.return_value = mock_path_obj
        
        mock_access.return_value = True
        mock_getsize.return_value = 1000
        
        # Mock LLM response
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
        
        # Mock PDF filler
        mock_filler_instance = Mock()
        mock_filler_instance.fill_form.return_value = "output.pdf"
        mock_filler.return_value = mock_filler_instance
        
        # Execute
        controller = Controller()
        path, review_flag = controller.fill_form(
            user_input="John Doe works as Manager",
            fields=["name", "title"],
            pdf_form_path="template.pdf"
        )
        
        # Verify
        assert path == "output.pdf"
        assert review_flag is False  # All fields present
        assert mock_filler_instance.fill_form.called

    
    @patch('src.file_manipulator.Filler')
    @patch('src.llm.requests.Session')
    @patch('pathlib.Path')
    @patch('os.access')
    @patch('os.path.getsize')
    def test_full_flow_with_fallback(
        self, mock_getsize, mock_access, mock_path, mock_session, mock_filler
    ):
        """Test complete flow with fallback to old method."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = True
        mock_path_obj.resolve.return_value = mock_path_obj
        mock_path.return_value = mock_path_obj
        
        mock_access.return_value = True
        mock_getsize.return_value = 1000
        
        # Mock LLM responses - first fails, then succeeds with old method
        call_count = [0]
        
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            mock_response = Mock()
            if call_count[0] == 1:
                # First call (structured) returns invalid JSON
                mock_response.text = 'invalid json'
                mock_response.json.return_value = {"response": 'invalid json'}
            else:
                # Subsequent calls (old method) return valid responses
                mock_response.text = '{"response": "John Doe"}'
                mock_response.json.return_value = {"response": "John Doe"}
            mock_response.headers.get.return_value = None
            mock_response.raise_for_status = Mock()
            return mock_response
        
        mock_session_instance = Mock()
        mock_session_instance.post.side_effect = mock_post
        mock_session.return_value = mock_session_instance
        
        # Mock PDF filler
        mock_filler_instance = Mock()
        mock_filler_instance.fill_form.return_value = "output.pdf"
        mock_filler.return_value = mock_filler_instance
        
        # Execute
        controller = Controller()
        path, review_flag = controller.fill_form(
            user_input="John Doe works as Manager",
            fields=["name", "title"],
            pdf_form_path="template.pdf"
        )
        
        # Verify
        assert path == "output.pdf"
        assert mock_filler_instance.fill_form.called
        assert review_flag is False  # Both fields should be present (John Doe, Manager)
        # Should have made multiple calls (structured + fallback)
        assert call_count[0] > 1
    
    @patch('src.file_manipulator.Filler')
    @patch('src.llm.requests.Session')
    @patch('pathlib.Path')
    @patch('os.access')
    @patch('os.path.getsize')
    def test_full_flow_requires_review(
        self, mock_getsize, mock_access, mock_path, mock_session, mock_filler
    ):
        """Test flow with missing data requiring review."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = True
        mock_path_obj.resolve.return_value = mock_path_obj
        mock_path.return_value = mock_path_obj
        
        mock_access.return_value = True
        mock_getsize.return_value = 1000
        
        # Mock LLM response with missing field
        mock_response = Mock()
        mock_response.text = '{"name": "John Doe", "title": "-1"}'
        mock_response.json.return_value = {
            "response": '{"name": "John Doe", "title": "-1"}'
        }
        mock_response.headers.get.return_value = None
        mock_response.raise_for_status = Mock()
        
        mock_session_instance = Mock()
        mock_session_instance.post.return_value = mock_response
        mock_session.return_value = mock_session_instance
        
        # Mock PDF filler
        mock_filler_instance = Mock()
        mock_filler_instance.fill_form.return_value = "output.pdf"
        mock_filler.return_value = mock_filler_instance
        
        # Execute
        controller = Controller()
        path, review_flag = controller.fill_form(
            user_input="John Doe",
            fields=["name", "title"],
            pdf_form_path="template.pdf"
        )
        
        # Verify
        assert path == "output.pdf"
        assert review_flag is True  # Missing title field
