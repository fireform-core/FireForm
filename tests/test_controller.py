from src.controller import Controller


def test_fill_form_validation_fail(monkeypatch):
    controller = Controller()

    def mock_fill_form(user_input, fields, pdf_form_path):
        return {
            "incident_type": "",  # invalid (empty)
            "location": "Downtown",
            "incident_time": "2026-03-20T10:30:00",
            "units_involved": ["Unit 42"],
            "summary": "Minor incident reported"
        }

    monkeypatch.setattr(controller.file_manipulator, "fill_form", mock_fill_form)

    try:
        controller.fill_form("input", [], "file.pdf")
        assert False  # Should not reach here
    except ValueError:
        assert True
