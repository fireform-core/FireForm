import sys
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import SQLModel, Session, create_engine

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from api.db.models import Datatype, FormSubmission, ReportSchema, SchemaField, Template
from api.db.repositories import (
    add_template_to_schema,
    create_report_schema,
    create_template,
    get_schema_fields,
    update_schema_field,
)
from src.controller import Controller
from src.report_schema import ReportSchemaProcessor


test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session
    SQLModel.metadata.drop_all(test_engine)


class _FakeT2J:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get_data(self) -> dict[str, Any]:
        return self._data


def _setup_schema_with_two_templates(session: Session):
    schema = create_report_schema(
        session,
        ReportSchema(name="s1", description="d1", use_case="u1"),
    )

    # Each template uses its own PDF field names, but both map to canonical
    # names via SchemaField.canonical_name.
    t1 = create_template(
        session,
        Template(name="t1", fields={"name_f1": "x", "age_f1": "y"}, pdf_path="t1.pdf"),
    )
    t2 = create_template(
        session,
        Template(name="t2", fields={"name_f2": "x", "age_f2": "y"}, pdf_path="t2.pdf"),
    )

    add_template_to_schema(session=session, schema_id=schema.id, template_id=t1.id)
    add_template_to_schema(session=session, schema_id=schema.id, template_id=t2.id)

    fields = get_schema_fields(session=session, schema_id=schema.id)
    for f in fields:
        if f.field_name in {"name_f1", "name_f2"}:
            update_schema_field(
                session,
                schema_id=schema.id,
                field_id=f.id,
                updates={
                    "canonical_name": "name",
                    "required": True,
                    "data_type": Datatype.STRING,
                    "word_limit": 10,
                },
            )
        elif f.field_name in {"age_f1", "age_f2"}:
            update_schema_field(
                session,
                schema_id=schema.id,
                field_id=f.id,
                updates={
                    "canonical_name": "age",
                    "required": False,
                    "data_type": Datatype.INT,
                },
            )
        else:
            raise AssertionError(f"Unexpected field_name in fixture: {f.field_name}")

    return schema, t1, t2


def test_controller_fill_report_uses_report_schema_processor_and_fills_templates(session: Session):
    schema, t1, t2 = _setup_schema_with_two_templates(session)

    canonical_data = {"name": "Alice", "age": 30}
    seen: dict[str, Any] = {}

    class FakeLLM:
        def __init__(self):
            self._transcript_text = None
            self._target_fields = None

        def main_loop(self):
            # Capture what FileManipulator passed to LLM.
            seen["transcript_text"] = self._transcript_text
            seen["target_fields"] = self._target_fields
            return _FakeT2J(canonical_data)

    class FakeFiller:
        def __init__(self):
            self.calls: list[tuple[str, dict[str, str]]] = []

        def fill_form_by_name(self, pdf_form: str, field_values: dict[str, str]) -> str:
            self.calls.append((pdf_form, field_values))
            return f"{pdf_form}__filled"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.file_manipulator.os.path.exists", lambda _: True)
        mp.setattr("src.file_manipulator.LLM", FakeLLM)
        mp.setattr("src.file_manipulator.Filler", FakeFiller)

        controller = Controller()
        # Act
        output = controller.fill_report(session=session, user_input="hello world", schema_id=schema.id)

        # Assert output paths per template.
        assert output == {t1.id: "t1.pdf__filled", t2.id: "t2.pdf__filled"}

        # Assert report schema processor output shape was passed to LLM.
        target_fields = seen["target_fields"]
        assert "properties" in target_fields
        assert set(target_fields["properties"].keys()) == {"name", "age"}
        assert target_fields["properties"]["age"]["type"] == "integer"

        # Required list should include canonical field 'name' only.
        assert set(target_fields["required"]) == {"name"}

        assert seen["transcript_text"] == "hello world"


def test_controller_fill_form_delegates_to_file_manipulator(session: Session):
    controller = Controller()

    seen: dict[str, Any] = {}

    def fake_fill_form(user_input: str, fields: list, pdf_form_path: str):
        seen["user_input"] = user_input
        seen["fields"] = fields
        seen["pdf_form_path"] = pdf_form_path
        return "/out.pdf"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(controller.file_manipulator, "fill_form", fake_fill_form)

        out = controller.fill_form(user_input="u1", fields=["a", "b"], pdf_form_path="/in.pdf")

    assert out == "/out.pdf"
    assert seen == {"user_input": "u1", "fields": ["a", "b"], "pdf_form_path": "/in.pdf"}


def test_controller_create_template_delegates_to_file_manipulator(session: Session):
    controller = Controller()

    seen: dict[str, Any] = {}

    def fake_create_template(pdf_path: str):
        seen["pdf_path"] = pdf_path
        return "/out_template.pdf"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(controller.file_manipulator, "create_template", fake_create_template)

        out = controller.create_template(pdf_path="/in.pdf")

    assert out == "/out_template.pdf"
    assert seen == {"pdf_path": "/in.pdf"}


def test_controller_extract_template_fields_delegates_to_file_manipulator():
    controller = Controller()

    def fake_extract(pdf_path: str):
        assert pdf_path == "/tpl.pdf"
        return {"a": "string"}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            controller.file_manipulator,
            "extract_template_field_map",
            fake_extract,
        )
        out = controller.extract_template_fields("/tpl.pdf")

    assert out == {"a": "string"}

