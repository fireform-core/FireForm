def test_valid_data():
    data = {
        "incident_type": "Fire",
        "location": "Downtown",
        "incident_time": "2026-03-20 10:00",
        "units_involved": ["Unit1", "Unit2"],
        "summary": "Fire contained"
    }
    assert validate_extracted_data(data) == True

def test_wrong_type():
    data = {
        "incident_type": "Fire",
        "location": "Downtown",
        "incident_time": "2026-03-20 10:00",
        "units_involved": "Unit1",  # should be list
        "summary": "Fire contained"
    }
    assert validate_extracted_data(data) == False
