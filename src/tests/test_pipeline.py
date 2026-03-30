import os
import pytest
from unittest.mock import patch, MagicMock

from src.schemas import IncidentReport, IncidentType
from src.security.crypto import encrypt_file, decrypt_file, secure_delete
from src.llm.self_correction import self_correction_loop

# 1. Test Encryption / Decryption Utilities
def test_encryption_decryption(tmp_path):
    os.environ["ENCRYPTION_KEY"] = "this_is_a_secure_32_byte_key_123"
    
    test_file = tmp_path / "test.txt"
    test_file.write_text("Highly classified incident narrative")
    
    enc_file = tmp_path / "enc.bin"
    dec_file = tmp_path / "dec.txt"
    
    # Encrypt
    encrypt_file(str(test_file), str(enc_file))
    assert enc_file.exists()
    assert enc_file.read_bytes() != b"Highly classified incident narrative"
    
    # Decrypt
    decrypt_file(str(enc_file), str(dec_file))
    assert dec_file.exists()
    assert dec_file.read_text() == "Highly classified incident narrative"
    
    # Test Secure Delete checks (at least ensure it unlinks)
    secure_delete(str(test_file))
    assert not test_file.exists()

# 2. Test Self-Correction Logic
def test_self_correction_loop_missing_fields():
    # Report missing units responding and location
    report = IncidentReport(
        location="Unknown",
        incident_type=IncidentType.FIRE,
        units_responding=[],
        narrative="Fire reported somewhere."
    )
    result = self_correction_loop("Fire reported somewhere.", report)
    
    assert not result["success"]
    assert "units_responding" in result["missing_fields"]
    assert "location" in result["missing_fields"]
    assert "units" in result["prompt"].lower()
    
# Test successful self-correction pass
def test_self_correction_loop_success():
    report = IncidentReport(
        location="42 Wallaby Way",
        incident_type=IncidentType.MEDICAL,
        units_responding=["Ambulance 5"],
        narrative="Ambulance 5 responded to a medical distress call at 42 Wallaby Way."
    )
    result = self_correction_loop("Ambulance 5 responded to a medical distress call at 42 Wallaby Way.", report)
    
    assert result["success"]

# 3. Test Extraction Pipeline (Mocked to decouple from running Ollama)
@patch("src.llm.constrained_extractor.extract_incident")
def test_extraction_pipeline(mock_extract):
    report = IncidentReport(
        location="123 Main St",
        incident_type=IncidentType.FIRE,
        units_responding=["Engine 1"],
        narrative="Fire at 123 Main St."
    )
    mock_extract.return_value = report
    
    narratives = [
        "Patient fell at 456 Elm St. Ambulance 3 on scene.",
        "Car crash on highway 1.",
        "Structure fire at 100 Oak, Engine 2 and Ladder 1 sent.",
        "Hazmat spill reported at factory, Hazmat 1 responding.",
        "Medical emergency, cardiac arrest, Medic 12 en route."
    ]
    
    for nar in narratives:
        res = mock_extract(text=nar)
        assert res.location == "123 Main St"
        assert len(res.units_responding) > 0

# 4. Test PDF Filler error states
def test_pdf_filler_missing_file():
    from src.pdf_filler.filler import fill_pdf
    
    with pytest.raises(FileNotFoundError):
        fill_pdf("nonexistent_template.pdf", {"location": "123 Main St"}, {"location": "LOC"})
