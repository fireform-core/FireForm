from ast import For
from collections import defaultdict
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from api.db.models import (
    Template,
    FormSubmission,
    ReportSchema,
    ReportSchemaTemplate,
    SchemaField,
)

def create_template(session: Session, template: Template) -> Template:
    try:
        session.add(template)
        session.commit()
        session.refresh(template)
        return template
    except IntegrityError:
        raise

def get_template(session: Session, template_id: int) -> Template | None:
    return session.get(Template, template_id)

def update_template(session: Session, template_id: int, updates: dict) -> Template | None:
    template = session.get(Template, template_id)
    if not template:
        return None
    for key, value in updates.items():
        setattr(template, key, value)
    session.add(template)
    session.commit()
    session.refresh(template)
    return template

def list_templates(session: Session) -> list[Template]:
    return session.exec(select(Template)).all()

def delete_template(session: Session, template_id: int) -> bool:
    """Remove template and dependent rows (form submissions, schema links, schema fields)."""
    template = session.get(Template, template_id)
    if not template:
        return False

    for form in session.exec(
        select(FormSubmission).where(FormSubmission.template_id == template_id)
    ).all():
        session.delete(form)

    for junction in session.exec(
        select(ReportSchemaTemplate).where(
            ReportSchemaTemplate.template_id == template_id
        )
    ).all():
        for field in session.exec(
            select(SchemaField).where(
                SchemaField.report_schema_id == junction.report_schema_id,
                SchemaField.source_template_id == template_id,
            )
        ).all():
            session.delete(field)
        session.delete(junction)

    session.delete(template)
    session.commit()
    return True

def create_form(session: Session, form: FormSubmission) -> FormSubmission:
    session.add(form)
    session.commit()
    session.refresh(form)
    return form

def get_form(session: Session, form_id: int) -> FormSubmission:
    return session.get(FormSubmission, form_id)

def update_form(session: Session, form_id: int, updates: dict) -> FormSubmission | None:
    form = session.get(FormSubmission, form_id)
    if not form:
        return None
    for key, value in updates.items():
        setattr(form, key, value)
    session.add(form)
    session.commit()
    session.refresh(form)
    return form

def delete_form(session: Session, form_id: int) -> FormSubmission:
    form_submission = session.get(FormSubmission, form_id)
    if form_submission:
        session.delete(form_submission)
        session.commit()
        return True
    return False

def create_report_schema(session: Session, schema: ReportSchema) -> ReportSchema:
    try:
        session.add(schema)
        session.commit()
        session.refresh(schema)
        return schema
    except IntegrityError:
        raise

def get_report_schema(session: Session, schema_id: int) -> ReportSchema | None:
    return session.get(ReportSchema, schema_id)

def list_report_schemas(session: Session) -> list[ReportSchema]:
    return session.exec(select(ReportSchema)).all()

def update_report_schema(session: Session, schema_id: int, updates: dict) -> ReportSchema | None:
    schema = session.get(ReportSchema, schema_id)
    if not schema:
        return None
    for key, value in updates.items():
        setattr(schema, key, value)
    session.add(schema)
    session.commit()
    session.refresh(schema)
    return schema

def delete_report_schema(session: Session, schema_id: int) -> bool:
    schema = session.get(ReportSchema, schema_id)
    if not schema:
        return False

    fields = session.exec(
        select(SchemaField).where(SchemaField.report_schema_id == schema_id)
    ).all()
    for field in fields:
        session.delete(field)

    junctions = session.exec(
        select(ReportSchemaTemplate).where(
            ReportSchemaTemplate.report_schema_id == schema_id
        )
    ).all()
    for junction in junctions:
        session.delete(junction)

    session.delete(schema)
    session.commit()
    return True


def add_template_to_schema(
    session: Session, schema_id: int, template_id: int
) -> ReportSchemaTemplate:
    """Associate a template with a schema.

    Looks up `template.fields` and auto-creates a SchemaField for each field,
    pre-populated with `field_name` and `source_template_id`.
    Other metadata is left as defaults for the user to fill in later.
    """
    template = session.get(Template, template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found")

    schema = session.get(ReportSchema, schema_id)
    if not schema:
        raise ValueError(f"ReportSchema {schema_id} not found")

    # exists = session.exec(select(ReportSchemaTemplate).where(ReportSchemaTemplate.report_schema_id == schema_id, ReportSchemaTemplate.template_id == template_id)).first()
    # if exists:
    #     raise IntegrityError

    # Create the junction record (field_mapping starts empty, populated during canonization)
    junction = ReportSchemaTemplate(
        report_schema_id=schema_id,
        template_id=template_id,
    )

    session.add(junction)

    # Auto-create a SchemaField for each field in the template
    for field_name in template.fields:
        schema_field = SchemaField(
            report_schema_id=schema_id,
            field_name=field_name,
            source_template_id=template_id,
        )
        session.add(schema_field)

    session.commit()
    session.refresh(junction)
    return junction

def remove_template_from_schema(
    session: Session, schema_id: int, template_id: int
) -> bool:
    """Disassociate a template from a schema and remove its SchemaField entries."""
    junction = session.exec(
        select(ReportSchemaTemplate).where(
            ReportSchemaTemplate.report_schema_id == schema_id,
            ReportSchemaTemplate.template_id == template_id,
        )
    ).first()
    if not junction:
        return False

    fields = session.exec(
        select(SchemaField).where(
            SchemaField.report_schema_id == schema_id,
            SchemaField.source_template_id == template_id,
        )
    ).all()
    for field in fields:
        session.delete(field)

    session.delete(junction)
    session.commit()
    return True


def get_schema_fields(session: Session, schema_id: int) -> list[SchemaField]:
    return session.exec(
        select(SchemaField).where(SchemaField.report_schema_id == schema_id)
    ).all()

def get_schema_field(session: Session, field_id: int) -> SchemaField:
    return session.get(SchemaField, field_id)

def update_schema_field(session: Session, schema_id: int, field_id: int, updates: dict) -> SchemaField | None:
    """Update field metadata: description, data_type, word_limit, required, allowed_values.

    Validates that the field belongs to the given schema before updating,
    so the same template field in different schemas can have independent metadata.
    """
    field = session.get(SchemaField, field_id)
    if not field or field.report_schema_id != schema_id:
        return None
    for key, value in updates.items():
        setattr(field, key, value)
    session.add(field)
    session.commit()
    session.refresh(field)
    return field


# ── Template mapping (post-canonization) ─────────────────────────────────────

def update_template_mapping(
    session: Session, schema_id: int, template_id: int
) -> ReportSchemaTemplate | None:
    """Auto-generate and store the canonical → PDF field mapping after canonization.

    Builds the mapping by looking up all SchemaFields for this schema+template pair
    and mapping each field's canonical_name → field_name.
    """
    junction = session.exec(
        select(ReportSchemaTemplate).where(
            ReportSchemaTemplate.report_schema_id == schema_id,
            ReportSchemaTemplate.template_id == template_id,
        )
    ).first()
    if not junction:
        return None

    # Build mapping from SchemaFields that have been canonized
    fields = session.exec(
        select(SchemaField).where(
            SchemaField.report_schema_id == schema_id,
            SchemaField.source_template_id == template_id,
        )
    ).all()

    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for field in sorted(fields, key=lambda f: f.field_name):
        key = field.canonical_name if field.canonical_name else field.field_name
        grouped[key].append(field.field_name)

    # One PDF field -> store str; several sharing a canonical -> list (distribute handles both).
    field_mapping: dict = {}
    for key, names in grouped.items():
        field_mapping[key] = names[0] if len(names) == 1 else names

    junction.field_mapping = field_mapping
    session.add(junction)
    session.commit()
    session.refresh(junction)
    return junction

def get_field_mapping(session: Session, schema_id: int, template_id: int) -> ReportSchemaTemplate:
    junction = session.exec(select(ReportSchemaTemplate).where(ReportSchemaTemplate.report_schema_id == schema_id, ReportSchemaTemplate.template_id == template_id)).first()
    return junction.field_mapping
