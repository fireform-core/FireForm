"""Compatibility checking between extracted data and template schemas."""

from typing import Dict, Any, Set, Optional
from src.template_schema import (
    TemplateSchema,
    TemplateRegistry,
    CompatibilityReport,
    FieldType,
)


class CompatibilityChecker:
    """Validates extracted data against template schemas before filling."""
    
    def __init__(self, registry: TemplateRegistry):
        """Initialize compatibility checker with a template registry.
        
        Args:
            registry: TemplateRegistry containing registered templates.
        """
        self.registry = registry
    
    def check_compatibility(
        self,
        template_id: str,
        extracted_data: Dict[str, Any],
    ) -> CompatibilityReport:
        """Check if extracted data is compatible with a template.
        
        Args:
            template_id: ID of the template to validate against.
            extracted_data: Extracted field data to validate.
            
        Returns:
            CompatibilityReport with detailed validation results.
            
        Raises:
            ValueError: If template_id not found in registry.
        """
        template = self.registry.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found in registry")
        
        report = CompatibilityReport(template_id=template_id, compatible=True)
        
        # Track which fields we've seen
        extracted_field_names = set(extracted_data.keys())
        matched_template_fields = set()
        
        # Check each extracted field
        for extracted_name, extracted_value in extracted_data.items():
            canonical_name = template.resolve_field_name(extracted_name)
            
            if canonical_name is None:
                # Field not found in template
                report.extra_fields.add(extracted_name)
                report.unmapped_fields.add(extracted_name)
                report.compatible = False
            else:
                # Field found - validate it
                field_schema = template.fields[canonical_name]
                matched_template_fields.add(canonical_name)
                report.matched_fields.add(canonical_name)
                
                # Type validation
                type_issue = self._validate_field_type(
                    canonical_name,
                    extracted_value,
                    field_schema,
                )
                if type_issue:
                    report.type_mismatches[canonical_name] = type_issue
                    report.compatible = False
        
        # Check for missing required fields
        required_fields = template.get_required_fields()
        missing_required = required_fields - matched_template_fields
        if missing_required:
            report.missing_fields = missing_required
            report.compatible = False
        
        # Check dependencies
        for matched_field in matched_template_fields:
            field_schema = template.fields[matched_field]
            for dependency in field_schema.dependencies:
                if dependency not in matched_template_fields:
                    report.dependency_violations.append((matched_field, dependency))
                    report.compatible = False
        
        # Warnings for informational purposes
        if report.extra_fields:
            report.warnings.append(
                f"Found {len(report.extra_fields)} field(s) not in template schema"
            )
        
        if report.type_mismatches:
            report.warnings.append(
                f"Found {len(report.type_mismatches)} type mismatch(es)"
            )
        
        return report
    
    def check_family_compatibility(
        self,
        family: str,
        extracted_data: Dict[str, Any],
    ) -> Dict[str, CompatibilityReport]:
        """Check extracted data against all templates in a family.
        
        Args:
            family: Template family name.
            extracted_data: Extracted field data to validate.
            
        Returns:
            Dictionary mapping template_id to CompatibilityReport for each
            template in the family.
            
        Raises:
            ValueError: If family not found in registry.
        """
        templates = self.registry.get_templates_by_family(family)
        if not templates:
            raise ValueError(f"Family {family} not found in registry")
        
        reports = {}
        for template in templates:
            reports[template.template_id] = self.check_compatibility(
                template.template_id,
                extracted_data,
            )
        
        return reports
    
    def find_compatible_templates(
        self,
        extracted_data: Dict[str, Any],
        tolerance: int = 0,
    ) -> list[tuple[str, CompatibilityReport]]:
        """Find all compatible templates for extracted data.
        
        Args:
            extracted_data: Extracted field data.
            tolerance: Maximum number of incompatibilities allowed.
                Default 0 means only fully compatible templates.
        
        Returns:
            List of (template_id, CompatibilityReport) tuples sorted by
            compatibility score (best first).
        """
        results = []
        
        for template in self.registry.list_templates():
            report = self.check_compatibility(template.template_id, extracted_data)
            
            # Calculate compatibility score
            incompatibility_count = (
                len(report.missing_fields)
                + len(report.extra_fields)
                + len(report.type_mismatches)
                + len(report.dependency_violations)
            )
            
            if incompatibility_count <= tolerance:
                results.append((template.template_id, report))
        
        # Sort by compatibility score (compatible first, then by severity)
        results.sort(
            key=lambda x: (
                not x[1].compatible,  # Compatible templates first
                len(x[1].missing_fields),  # Fewer missing fields
                len(x[1].type_mismatches),  # Fewer type mismatches
                x[0],  # Deterministic tie-breaker: template_id
            ),
        )
        
        return results
    
    def _validate_field_type(
        self,
        field_name: str,
        value: Any,
        field_schema,
    ) -> Optional[str]:
        """Validate that a field value matches the expected type.
        
        Args:
            field_name: Name of the field being validated.
            value: The value to validate.
            field_schema: The FieldSchema with expected type information.
            
        Returns:
            Error message if validation fails, None if valid.
        """
        if value is None:
            return None
        
        value_str = str(value).strip()
        
        if field_schema.field_type == FieldType.EMAIL:
            if "@" not in value_str or "." not in value_str.split("@")[-1]:
                return f"Invalid email format: {value}"
        
        elif field_schema.field_type == FieldType.PHONE:
            # Basic phone validation: at least 7 digits
            digits = "".join(c for c in value_str if c.isdigit())
            if len(digits) < 7:
                return f"Invalid phone format (need 7+ digits): {value}"
        
        elif field_schema.field_type == FieldType.DATE:
            # Check for common date formats
            if not self._is_valid_date_format(value_str):
                return f"Invalid date format: {value}"
        
        elif field_schema.field_type == FieldType.NUMBER:
            try:
                float(value_str)
            except ValueError:
                return f"Invalid number: {value}"
        
        elif field_schema.field_type == FieldType.CHECKBOX:
            valid_checkbox_values = {"yes", "no", "true", "false", "1", "0", "checked", "unchecked"}
            if value_str.lower() not in valid_checkbox_values:
                return f"Invalid checkbox value: {value}"
        
        elif field_schema.field_type == FieldType.DROPDOWN:
            if field_schema.expected_values:
                if value_str not in field_schema.expected_values:
                    return f"Invalid dropdown value: {value}. Expected one of: {', '.join(field_schema.expected_values)}"
        
        elif field_schema.field_type == FieldType.TEXT:
            if field_schema.max_length and len(value_str) > field_schema.max_length:
                return f"Text exceeds max length ({field_schema.max_length}): {value}"
        
        return None
    
    @staticmethod
    def _is_valid_date_format(value: str) -> bool:
        """Check if a value appears to be a valid date format.
        
        Accepts common formats like:
        - YYYY-MM-DD
        - MM/DD/YYYY
        - DD/MM/YYYY
        - Month DD, YYYY
        """
        import re
        
        patterns = [
            r"^\d{1,2}/\d{1,2}/\d{4}$",  # MM/DD/YYYY or DD/MM/YYYY
            r"^\d{4}-\d{1,2}-\d{1,2}$",  # YYYY-MM-DD
            r"^[A-Za-z]+ \d{1,2}, \d{4}$",  # Month DD, YYYY
        ]
        
        return any(re.match(pattern, value) for pattern in patterns)
