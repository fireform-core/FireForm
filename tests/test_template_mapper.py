from src.template_mapper import TemplateMapper


def test_mapping_success():
    mapping = {
        "patient_name": "NameField",
        "age": "AgeField",
        "diagnosis": "DiagnosisField"
    }

    data = {
        "patient_name": "John Doe",
        "age": 45,
        "diagnosis": "Burn injury"
    }

    mapper = TemplateMapper(mapping)
    result = mapper.map_to_pdf_fields(data)

    assert result == {
        "NameField": "John Doe",
        "AgeField": 45,
        "DiagnosisField": "Burn injury"
    }


def test_missing_fields():
    mapping = {
        "patient_name": "NameField",
        "age": "AgeField",
        "diagnosis": "DiagnosisField"
    }

    data = {
        "patient_name": "John Doe"
    }

    mapper = TemplateMapper(mapping)
    result = mapper.map_to_pdf_fields(data)

    assert result == {
        "NameField": "John Doe"
    }
