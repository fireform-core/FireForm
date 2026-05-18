from src.controller import Controller


def test_fill_form_validation_fail(monkeypatch):
    controller = Controller()

    def mock_fill_form(user_input, fields, pdf_form_path):
        return {"patient_name": "", "age": 30, "diagnosis": "Flu"}

    monkeypatch.setattr(controller.file_manipulator, "fill_form", mock_fill_form)

    try:
        controller.fill_form("input", [], "file.pdf")
        assert False  # Should not reach here
    except ValueError:
        assert True
