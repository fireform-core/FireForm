import sys
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from api.db.models import Datatype, FormSubmission, ReportSchema, ReportSchemaTemplate, SchemaField, Template
from api.db.repositories import (
    add_template_to_schema,
    create_form,
    create_report_schema,
    create_template,
    delete_form,
    delete_report_schema,
    delete_template,
    get_form,
    get_report_schema,
    get_schema_fields,
    get_template,
    list_report_schemas,
    remove_template_from_schema,
    update_form,
    update_report_schema,
    update_schema_field,
    update_template,
    update_template_mapping,
)


test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session
    SQLModel.metadata.drop_all(test_engine)


def _mk_schema(session: Session, name: str = "schema") -> ReportSchema:
    return create_report_schema(session, ReportSchema(name=name, description=f"{name}-desc", use_case=f"{name}-use"))


def _mk_template(session: Session, name: str = "template", fields: dict | None = None) -> Template:
    return create_template(
        session,
        Template(name=name, fields=fields if fields is not None else {"f1": "v1"}, pdf_path=f"{name}.pdf"),
    )


def test_create_get_update_and_delete_template(session: Session):
    created = _mk_template(session, "t-main", {"a": "b"})

    # test that creation is accurate
    assert created.id is not None
    assert created.name == "t-main"
    assert created.fields == {"a": "b"}
    assert created.pdf_path == "t-main.pdf"

    fetched = get_template(session, created.id)

    # test whether the fetched and created templates match
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "t-main"
    assert fetched.fields == {"a": "b"}
    assert fetched.pdf_path == "t-main.pdf"

    # test whether updates are persistent and are done correctly
    _ = update_template(session, fetched.id, { "name" : "updated-name", "fields" :{"ua" : "ub"}, "pdf_path" : "t-updated.pdf"})
    updated = get_template(session, fetched.id)
    assert updated is not None
    assert updated.id == created.id
    assert updated.name == "updated-name"
    assert updated.fields == {"ua": "ub"}
    assert updated.pdf_path == "t-updated.pdf"

    # test that deleting works and double deleting does not work
    assert delete_template(session, fetched.id) is True
    assert delete_template(session, fetched.id) is False

    # test that getting a template that does not exist does not work
    assert get_template(session, 999999) is None


def test_delete_template_cascades_forms_and_schema_links(session: Session):
    schema = _mk_schema(session, "s-cascade")
    tpl = _mk_template(session, "t-cascade", {"a": "string", "b": "string"})
    add_template_to_schema(session, schema_id=schema.id, template_id=tpl.id)
    assert len(get_schema_fields(session, schema.id)) == 2

    form = create_form(
        session,
        FormSubmission(
            template_id=tpl.id,
            input_text="hi",
            output_pdf_path="/out.pdf",
        ),
    )

    assert delete_template(session, tpl.id) is True
    assert get_template(session, tpl.id) is None
    assert get_schema_fields(session, schema.id) == []
    assert get_form(session, form.id) is None
    assert (
        session.exec(
            select(ReportSchemaTemplate).where(
                ReportSchemaTemplate.template_id == tpl.id
            )
        ).first()
        is None
    )


def test_create_get_update_and_delete_form_submission(session: Session):
    form = FormSubmission(template_id=123, input_text="sample input", output_pdf_path="/tmp/out.pdf")
    created = create_form(session, form)

    # test creation of form is correct
    assert created.id is not None
    assert created.template_id == 123
    assert created.input_text == "sample input"
    assert created.output_pdf_path == "/tmp/out.pdf"

    fetched = get_form(session, created.id)

    # test whether the fetched and created forms match
    assert fetched.id == created.id
    assert fetched.template_id == 123
    assert fetched.input_text == "sample input"
    assert fetched.output_pdf_path == "/tmp/out.pdf"

    # test whether updates are persistent and are done correctly
    _ = update_form(session, fetched.id, { "template_id" : 321, "input_text" : "input sample", "output_pdf_path" : "t-updated.pdf"})
    updated = get_form(session, fetched.id)
    assert updated is not None
    assert updated.id == created.id
    assert updated.template_id == 321
    assert updated.input_text == "input sample"
    assert updated.output_pdf_path == "t-updated.pdf"

    # test that deletion works and double deletion does not work
    assert delete_form(session, fetched.id) is True
    assert delete_form(session, fetched.id) is False

    # test that getting a template that does not exist does not work
    assert get_form(session, 999999) is None


def test_create_get_list_update_and_delete_report_schema(session: Session):
    s1 = _mk_schema(session, "s1")
    s2 = _mk_schema(session, "s2")

    # implicitly tests schema creation and directly tests fetching
    fetched = get_report_schema(session, s1.id)
    assert fetched is not None
    assert fetched.id == s1.id
    assert fetched.name == "s1"
    assert fetched.description == "s1-desc"
    assert fetched.use_case == "s1-use"

    # test getting a template that does not exist does not work
    assert get_report_schema(session, 999999) is None

    # test listing all schemas works correctly
    listed = list_report_schemas(session)
    assert {s.name for s in listed} == {"s1", "s2"}

    # test updating a schema works correctly
    updated = update_report_schema(session, s1.id, {"name": "s1-new", "use_case": "u-new"})
    assert updated is not None
    assert updated.name == "s1-new"
    assert updated.description == "s1-desc"
    assert updated.use_case == "u-new"

    # test updating a schema that does not exist does not work
    assert update_report_schema(session, 999999, {"name": "x"}) is None


def test_add_template_to_schema_creates_junction_and_schema_fields(session: Session):
    schema = _mk_schema(session)
    template = _mk_template(session, fields={"field1": "x", "field2": "y"})

    _ = add_template_to_schema(session, schema.id, template.id)
    junction = session.get(ReportSchemaTemplate, _.id)

    # assert that the junction was created and created with the correct details
    assert junction is not None
    assert junction.report_schema_id == schema.id
    assert junction.template_id == template.id

    fields = get_schema_fields(session, schema.id)

    # assert correct number of fields were created
    assert len(fields) == 2

    # assert all fields were created using correct details
    assert {f.field_name for f in fields} == {"field1", "field2"}
    assert {f.source_template_id for f in fields} == {template.id}
    assert {f.report_schema_id for f in fields} == {schema.id}

def test_delete_report_schema_deletes_schema_fields_and_junctions(session: Session):
    schema = _mk_schema(session, "cascade")
    t1 = _mk_template(session, "t1", {"f1": "v1", "f2": "v2"})
    t2 = _mk_template(session, "t2", {"f3": "v3"})
    add_template_to_schema(session, schema.id, t1.id)
    add_template_to_schema(session, schema.id, t2.id)

    assert len(get_schema_fields(session, schema.id)) == 3
    assert session.query(ReportSchemaTemplate).count() == 2

    # test deletion works correctly and fields as well as juncitions are deleted
    assert delete_report_schema(session, schema.id) is True
    assert get_report_schema(session, schema.id) is None
    assert get_schema_fields(session, schema.id) == []
    assert session.query(ReportSchemaTemplate).count() == 0

    # test double deletion and deleting schemas that do not exist
    assert delete_report_schema(session, schema.id) is False
    assert delete_report_schema(session, 424242) is False


def test_add_template_to_schema_supports_empty_template_fields(session: Session):
    schema = _mk_schema(session, "empty-fields")
    template = _mk_template(session, "empty-template", fields={})

    junction = add_template_to_schema(session, schema.id, template.id)

    assert junction.id is not None
    assert get_schema_fields(session, schema.id) == []

def test_add_template_to_schema_raises_for_missing_template_or_schema(session: Session):
    schema = _mk_schema(session, "schema-only")
    template = _mk_template(session, "template-only")

    with pytest.raises(ValueError, match="Template .* not found"):
        add_template_to_schema(session, schema.id, 999999)

    with pytest.raises(ValueError, match="ReportSchema .* not found"):
        add_template_to_schema(session, 999999, template.id)


def test_add_template_to_schema_duplicate_association_creates_extra_rows(session: Session):
    schema = _mk_schema(session, "dup-schema")
    template = _mk_template(session, "dup-template", {"f1": "v1"})

    add_template_to_schema(session, schema.id, template.id)
    add_template_to_schema(session, schema.id, template.id)

    assert session.query(ReportSchemaTemplate).count() == 2
    fields = get_schema_fields(session, schema.id)
    assert len(fields) == 2
    assert all(field.field_name == "f1" for field in fields)


def test_remove_template_from_schema_removes_only_target_template_rows(session: Session):
    schema = _mk_schema(session, "remove")
    t1 = _mk_template(session, "t1", {"a": "1"})
    t2 = _mk_template(session, "t2", {"b": "2"})
    add_template_to_schema(session, schema.id, t1.id)
    add_template_to_schema(session, schema.id, t2.id)

    assert remove_template_from_schema(session, schema.id, t1.id) is True

    remaining_fields = get_schema_fields(session, schema.id)
    assert len(remaining_fields) == 1
    assert remaining_fields[0].field_name == "b"
    assert remaining_fields[0].source_template_id == t2.id
    assert remove_template_from_schema(session, schema.id, t1.id) is False
    assert remove_template_from_schema(session, 101010, 202020) is False


def test_get_schema_fields_returns_fields_for_only_given_schema(session: Session):
    s1 = _mk_schema(session, "s1")
    s2 = _mk_schema(session, "s2")
    t1 = _mk_template(session, "t1", {"f1": "v1", "f2": "v2"})
    t2 = _mk_template(session, "t2", {"x": "y"})
    add_template_to_schema(session, s1.id, t1.id)
    add_template_to_schema(session, s2.id, t2.id)

    s1_fields = get_schema_fields(session, s1.id)
    assert len(s1_fields) == 2
    assert {f.field_name for f in s1_fields} == {"f1", "f2"}


def test_update_schema_field_updates_all_supported_metadata(session: Session):
    schema = _mk_schema(session, "meta")
    template = _mk_template(session, "meta-t", {"status": "draft"})
    add_template_to_schema(session, schema.id, template.id)
    field = get_schema_fields(session, schema.id)[0]

    updates = {
        "description": "Status of the workflow",
        "data_type": Datatype.ENUM,
        "word_limit": 3,
        "required": True,
        "allowed_values": {"values": ["draft", "final"]},
        "canonical_name": "status_canonical",
    }
    updated = update_schema_field(session, schema.id, field.id, updates)
    assert updated is not None

    refreshed = session.get(SchemaField, field.id)
    assert refreshed is not None
    assert refreshed.description == updates["description"]
    assert refreshed.data_type == updates["data_type"]
    assert refreshed.word_limit == updates["word_limit"]
    assert refreshed.required is True
    assert refreshed.allowed_values == updates["allowed_values"]
    assert refreshed.canonical_name == updates["canonical_name"]


def test_update_schema_field_returns_none_for_missing_or_mismatched_field(session: Session):
    s1 = _mk_schema(session, "s1")
    s2 = _mk_schema(session, "s2")
    t = _mk_template(session, "t", {"f1": "v1"})
    add_template_to_schema(session, s1.id, t.id)
    field = get_schema_fields(session, s1.id)[0]

    assert update_schema_field(session, s2.id, field.id, {"description": "x"}) is None
    assert update_schema_field(session, s1.id, 999999, {"description": "x"}) is None


def test_update_template_mapping_uses_canonical_name_or_fallback_field_name(session: Session):
    schema = _mk_schema(session, "mapping")
    template = _mk_template(session, "mapping-t", {"f1": "v1", "f2": "v2"})
    add_template_to_schema(session, schema.id, template.id)
    fields = sorted(get_schema_fields(session, schema.id), key=lambda f: f.field_name)

    update_schema_field(session, schema.id, fields[0].id, {"canonical_name": "canon_f1"})
    # fields[1] intentionally left without canonical_name to test fallback

    junction = update_template_mapping(session, schema.id, template.id)
    assert junction is not None
    assert junction.field_mapping == {"canon_f1": "f1", "f2": "f2"}


def test_update_template_mapping_returns_none_when_junction_missing(session: Session):
    schema = _mk_schema(session, "missing-junction")
    template = _mk_template(session, "missing-junction-t")

    # No call to add_template_to_schema, so no junction exists.
    assert update_template_mapping(session, schema.id, template.id) is None
