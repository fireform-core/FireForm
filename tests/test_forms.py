import pytest
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from llm import LLM


def test_main_loop_batched():
    """
    Test the batched LLM extraction method with sample fields.
    This test verifies that main_loop_batched() can process multiple fields
    in a single API call and return valid JSON data.
    
    Note: This test requires Ollama with Mistral model running locally.
    Run 'make pull-model' and 'make up' before executing this test.
    """
    # Sample transcript text for extraction
    sample_transcript = """
    Officer reporting incident at 123 Main Street. Two victims involved: 
    John Smith with minor injuries and Jane Doe with serious injuries. 
    Medical aid rendered by paramedic team. Incident time approximately 2:30 PM.
    """
    
    # Sample PDF fields to extract
    sample_fields = {
        "incident_location": "text",
        "victim_names": "text", 
        "injury_count": "number",
        "medical_aid": "text"
    }
    
    # Create LLM instance with sample data
    llm_instance = LLM(
        transcript_text=sample_transcript,
        target_fields=sample_fields
    )
    
    try:
        # Test batched extraction method
        result = llm_instance.main_loop_batched()
        
        # Verify that the method returns self for chaining
        assert result is llm_instance, "Method should return self for chaining"
        
        # Verify that _json is populated and is a dictionary
        extracted_data = llm_instance.get_data()
        assert isinstance(extracted_data, dict), "Extracted data should be a dictionary"
        
        # Verify that we have data for our sample fields
        assert len(extracted_data) > 0, "Should have extracted some data"
        
        # Print success message for manual verification
        print("✅ Batched extraction test PASSED")
        print(f"Extracted {len(extracted_data)} fields:")
        for field, value in extracted_data.items():
            print(f"  - {field}: {value}")
            
    except ConnectionError as e:
        pytest.skip(f"Ollama not available: {e}. Run 'make up' to start services.")
    except Exception as e:
        pytest.fail(f"Batched extraction test failed: {e}")


def test_submit_form(client):
    # Original test kept for compatibility (currently commented out)
    pass
    # First create a template
    # form_payload = {
    #     "template_id": 3,
    #     "input_text": "Hi. The employee's name is John Doe. His job title is managing director. His department supervisor is Jane Doe. His phone number is 123456. His email is jdoe@ucsc.edu. The signature is <Mamañema>, and the date is 01/02/2005",
    # }

    # template_res = client.post("/templates/", json=template_payload)
    # template_id = template_res.json()["id"]

    # # Submit a form
    # form_payload = {
    #     "template_id": template_id,
    #     "data": {"rating": 5, "comment": "Great service"},
    # }

    # response = client.post("/forms/", json=form_payload)

    # assert response.status_code == 200

    # data = response.json()
    # assert data["id"] is not None
    # assert data["template_id"] == template_id
    # assert data["data"] == form_payload["data"]
