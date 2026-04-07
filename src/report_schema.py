from sqlmodel import Session, select
from typing import Any
from api.db.models import SchemaField, ReportSchemaTemplate, Datatype
from api.schemas.report_class import CanonicalSchema, CanonicalFieldEntry, SchemaFieldResponse
from api.db.repositories import update_template_mapping, get_report_schema


class ReportSchemaProcessor:
    @staticmethod
    def canonize(session: Session, schema_id: int) -> CanonicalSchema:
        """Group fields by their canonical names (falling back to original names)."""
        schema = get_report_schema(session, schema_id)
        if not schema:
            raise ValueError(f"ReportSchema {schema_id} not found")

        # 1. Fetch all fields for this schema
        fields = session.exec(
            select(SchemaField).where(SchemaField.report_schema_id == schema_id)
        ).all()

        # 2. Group fields by their effective canonical name
        groups: dict[str, list[SchemaField]] = {}
        
        for field in fields:
            # The manual override rule: If no canonical name is set, use the raw field name
            effective_name = field.canonical_name if field.canonical_name else field.field_name
            
            if effective_name not in groups:
                 groups[effective_name] = []
            groups[effective_name].append(field)

        # 3. Build the CanonicalSchema representation
        canonical_fields = []
        for effective_name, source_fields in groups.items():
            # Use metadata from the first field in the group as the canonical metadata
            # (In a more complex system, we might merge these or let the user elect a "primary" field)
            primary = source_fields[0]
            
            canonical_fields.append(
                CanonicalFieldEntry(
                    canonical_name=effective_name,
                    description=primary.description,
                    data_type=primary.data_type,
                    word_limit=primary.word_limit,
                    required=primary.required,
                    allowed_values=primary.allowed_values,
                    source_fields=[SchemaFieldResponse.model_validate(f) for f in source_fields]
                )
            )

        # 4. Update the junction tables so they know how to map back
        # We need to do this per-template
        template_ids = {f.source_template_id for f in fields}
        for t_id in template_ids:
            update_template_mapping(session, schema_id, t_id)

        return CanonicalSchema(
            report_schema_id=schema_id,
            canonical_fields=canonical_fields
        )

    @staticmethod
    def build_extraction_target(canonical_schema: CanonicalSchema) -> dict[str, Any]:
        """Convert the CanonicalSchema into a JSON schema dict for LLM function calling."""
        properties = {}
        required = []

        type_mapping = {
            Datatype.STRING: "string",
            Datatype.INT: "integer",
            Datatype.DATE: "string", # Represent dates as strings for LLM
            Datatype.ENUM: "string"  # Enums are strings restricted by allowed_values
        }

        for field in canonical_schema.canonical_fields:
            field_def = {
                "type": type_mapping.get(field.data_type, "string"),
                "description": field.description
            }

            if field.data_type == Datatype.ENUM and field.allowed_values and "values" in field.allowed_values:
                field_def["enum"] = field.allowed_values["values"]
                
            if field.word_limit:
                 field_def["description"] += f" (Maximum {field.word_limit} words)"

            properties[field.canonical_name] = field_def

            if field.required:
                required.append(field.canonical_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }

    @staticmethod
    def distribute(
        session: Session, schema_id: int, canonical_data: dict[str, Any]
    ) -> dict[int, dict[str, Any]]:
        """Map canonical extraction output back to individual template fields."""
        junctions = session.exec(
            select(ReportSchemaTemplate).where(
                ReportSchemaTemplate.report_schema_id == schema_id
            )
        ).all()

        distribution = {}
        
        for junction in junctions:
            template_id = junction.template_id
            mapping = junction.field_mapping or {}
            
            template_data = {}
            for canonical_name, pdf_targets in mapping.items():
                if canonical_name not in canonical_data:
                    continue
                names = (
                    pdf_targets
                    if isinstance(pdf_targets, list)
                    else [pdf_targets]
                )
                for pdf_field_name in names:
                    template_data[pdf_field_name] = canonical_data[canonical_name]
                    
            distribution[template_id] = template_data
            
        return distribution
