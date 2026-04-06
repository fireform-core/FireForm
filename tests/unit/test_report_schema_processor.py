import sys
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from api.db.models import Datatype, ReportSchema, ReportSchemaTemplate, Template
from api.db.repositories import (
    add_template_to_schema,
    create_report_schema,
    create_template,
    get_schema_fields,
    update_schema_field,
)
from api.schemas.report_class import CanonicalFieldEntry, CanonicalSchema, SchemaFieldResponse
from src.report_schema import ReportSchemaProcessor


test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session
    SQLModel.metadata.drop_all(test_engine)


def _setup_schema_with_two_templates(session: Session):
    schema = create_report_schema(session, ReportSchema(name="s1", description="d1", use_case="u1"))
    t1 = create_template(session, Template(name="t1", fields={"f1": "v1", "f2": "v2"}, pdf_path="t1.pdf"))
    t2 = create_template(session, Template(name="t2", fields={"f3": "v3", "f4": "v4"}, pdf_path="t2.pdf"))
    add_template_to_schema(session=session, template_id=t1.id, schema_id=schema.id)
    add_template_to_schema(session=session, template_id=t2.id, schema_id=schema.id)
    return schema, t1, t2


def test_canonize_raises_for_missing_schema(session: Session):
    with pytest.raises(ValueError, match="ReportSchema .* not found"):
        ReportSchemaProcessor.canonize(session=session, schema_id=999999)


def test_canonize_groups_fields_and_updates_junction_mappings(session: Session):
    schema, t1, t2 = _setup_schema_with_two_templates(session)
    fields = sorted(get_schema_fields(session=session, schema_id=schema.id), key=lambda f: f.field_name)
    assert len(fields) == 4

    # Merge f1 + f2 into one canonical field.
    update_schema_field(session, schema.id, fields[0].id, {"canonical_name": "person_name"})
    update_schema_field(session, schema.id, fields[1].id, {"canonical_name": "person_name"})

    canonical = ReportSchemaProcessor.canonize(session=session, schema_id=schema.id)
    canonical_by_name = {f.canonical_name: f for f in canonical.canonical_fields}

    assert canonical.report_schema_id == schema.id
    assert set(canonical_by_name.keys()) == {"person_name", "f3", "f4"}
    assert len(canonical_by_name["person_name"].source_fields) == 2

    t1_junction = session.query(ReportSchemaTemplate).filter(
        ReportSchemaTemplate.report_schema_id == schema.id,
        ReportSchemaTemplate.template_id == t1.id,
    ).one()
    t2_junction = session.query(ReportSchemaTemplate).filter(
        ReportSchemaTemplate.report_schema_id == schema.id,
        ReportSchemaTemplate.template_id == t2.id,
    ).one()
    assert t1_junction.field_mapping == {"person_name": ["f1", "f2"]}
    assert t2_junction.field_mapping == {"f3": "f3", "f4": "f4"}


def test_canonize_uses_raw_field_name_when_canonical_name_missing(session: Session):
    schema, _, _ = _setup_schema_with_two_templates(session)
    canonical = ReportSchemaProcessor.canonize(session=session, schema_id=schema.id)
    names = {f.canonical_name for f in canonical.canonical_fields}
    assert names == {"f1", "f2", "f3", "f4"}


def test_build_extraction_target_maps_types_required_enum_and_word_limit():
    canonical_schema = CanonicalSchema(
        report_schema_id=1,
        canonical_fields=[
            CanonicalFieldEntry(
                canonical_name="name",
                description="Patient name",
                data_type=Datatype.STRING,
                word_limit=4,
                required=True,
                allowed_values=None,
                source_fields=[],
            ),
            CanonicalFieldEntry(
                canonical_name="age",
                description="Patient age",
                data_type=Datatype.INT,
                word_limit=None,
                required=True,
                allowed_values=None,
                source_fields=[],
            ),
            CanonicalFieldEntry(
                canonical_name="visit_date",
                description="Visit date",
                data_type=Datatype.DATE,
                word_limit=None,
                required=False,
                allowed_values=None,
                source_fields=[],
            ),
            CanonicalFieldEntry(
                canonical_name="status",
                description="Final status",
                data_type=Datatype.ENUM,
                word_limit=None,
                required=False,
                allowed_values={"values": ["draft", "final"]},
                source_fields=[],
            ),
            CanonicalFieldEntry(
                canonical_name="enum_without_values",
                description="Bad enum metadata",
                data_type=Datatype.ENUM,
                word_limit=None,
                required=False,
                allowed_values={"other": [1, 2]},
                source_fields=[],
            ),
        ],
    )

    target = ReportSchemaProcessor.build_extraction_target(canonical_schema)

    assert target["type"] == "object"
    assert set(target["properties"].keys()) == {
        "name",
        "age",
        "visit_date",
        "status",
        "enum_without_values",
    }
    assert set(target["required"]) == {"name", "age"}
    assert target["properties"]["name"]["type"] == "string"
    assert "Maximum 4 words" in target["properties"]["name"]["description"]
    assert target["properties"]["age"]["type"] == "integer"
    assert target["properties"]["visit_date"]["type"] == "string"
    assert target["properties"]["status"]["type"] == "string"
    assert target["properties"]["status"]["enum"] == ["draft", "final"]
    assert "enum" not in target["properties"]["enum_without_values"]


def test_distribute_returns_per_template_payload_from_mapping(session: Session):
    schema, t1, t2 = _setup_schema_with_two_templates(session)
    fields = sorted(get_schema_fields(session=session, schema_id=schema.id), key=lambda f: f.field_name)

    update_schema_field(session, schema.id, fields[0].id, {"canonical_name": "a"})
    update_schema_field(session, schema.id, fields[1].id, {"canonical_name": "b"})
    update_schema_field(session, schema.id, fields[2].id, {"canonical_name": "x"})
    update_schema_field(session, schema.id, fields[3].id, {"canonical_name": "y"})
    ReportSchemaProcessor.canonize(session=session, schema_id=schema.id)

    canonical_data = {"a": "A", "b": "B", "x": "X", "ignored": "IGNORED"}
    distribution = ReportSchemaProcessor.distribute(session, schema.id, canonical_data)

    assert distribution[t1.id] == {"f1": "A", "f2": "B"}
    assert distribution[t2.id] == {"f3": "X"}


def test_distribute_handles_missing_junctions_or_empty_mappings(session: Session):
    schema = create_report_schema(session, ReportSchema(name="s-empty", description="d", use_case="u"))

    assert ReportSchemaProcessor.distribute(session, schema.id, {"x": 1}) == {}

    # Create a template + junction, but no canonical mapping update.
    t1 = create_template(session, Template(name="t-empty", fields={"f1": "v1"}, pdf_path="t-empty.pdf"))
    add_template_to_schema(session, schema_id=schema.id, template_id=t1.id)

    # field_mapping defaults to {}, so distribution should contain empty payload for template.
    distribution = ReportSchemaProcessor.distribute(session, schema.id, {"x": 1})
    assert distribution == {t1.id: {}}