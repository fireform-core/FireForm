"""Template schema registry and compatibility checking for FireForm.

Provides template metadata management describing required fields, aliases,
expected data types, and form versioning. Enables predictable behavior and
reproducibility across multiple PDF templates.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum


class FieldType(Enum):
    """Enumeration of supported field data types."""
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    DATE = "date"
    NUMBER = "number"
    CHECKBOX = "checkbox"
    DROPDOWN = "dropdown"
    UNKNOWN = "unknown"


@dataclass
class FieldSchema:
    """Schema definition for a single form field."""
    name: str
    """Primary field name as it appears in the PDF form."""
    
    field_type: FieldType = FieldType.TEXT
    """Expected data type of the field."""
    
    required: bool = False
    """Whether the field must be present in extraction."""
    
    aliases: List[str] = field(default_factory=list)
    """Alternative names this field might appear as in extracted data."""
    
    expected_values: Optional[List[str]] = None
    """Enumerated valid values for dropdown/select fields."""
    
    dependencies: List[str] = field(default_factory=list)
    """Other fields that must be present if this field is filled."""
    
    max_length: Optional[int] = None
    """Maximum character length for text fields."""
    
    description: str = ""
    """Human-readable description of the field."""
    
    def get_all_names(self) -> Set[str]:
        """Return all possible names (primary + aliases) for this field."""
        return {self.name} | set(self.aliases)


@dataclass
class TemplateSchema:
    """Complete schema definition for a PDF template."""
    template_id: str
    """Unique identifier for this template version."""
    
    template_name: str
    """Human-readable name of the template."""
    
    version: str
    """Semantic version of the template (e.g., '1.0.0')."""
    
    family: str
    """Template family for grouping related templates."""
    
    fields: Dict[str, FieldSchema] = field(default_factory=dict)
    """Mapping of field names to their schemas."""
    
    description: str = ""
    """Description of the template purpose and use cases."""
    
    created_at: str = ""
    """ISO timestamp when template schema was created."""
    
    metadata: Dict[str, str] = field(default_factory=dict)
    """Additional custom metadata about the template."""
    
    def get_required_fields(self) -> Set[str]:
        """Return set of all required field names."""
        return {name for name, schema in self.fields.items() if schema.required}
    
    def get_all_field_names(self) -> Set[str]:
        """Return set of all possible field names (primary + all aliases)."""
        all_names = set()
        for schema in self.fields.values():
            all_names.update(schema.get_all_names())
        return all_names
    
    def resolve_field_name(self, extracted_name: str) -> Optional[str]:
        """Map an extracted field name to the canonical field name in schema.
        
        Args:
            extracted_name: Field name from extraction.
            
        Returns:
            Canonical field name if found, None otherwise.
        """
        # Exact match
        if extracted_name in self.fields:
            return extracted_name
        
        # Check aliases
        for canonical_name, schema in self.fields.items():
            if extracted_name in schema.aliases:
                return canonical_name
        
        return None


@dataclass
class CompatibilityReport:
    """Results of compatibility check between extracted data and template schema."""
    template_id: str
    """ID of the template being checked against."""
    
    compatible: bool
    """Whether extracted data is compatible with template."""
    
    missing_fields: Set[str] = field(default_factory=set)
    """Required fields that are missing from extraction."""
    
    extra_fields: Set[str] = field(default_factory=set)
    """Extracted fields that don't match any template field."""
    
    unmapped_fields: Set[str] = field(default_factory=set)
    """Extracted fields that couldn't be mapped to template fields."""
    
    type_mismatches: Dict[str, str] = field(default_factory=dict)
    """Fields where extracted value type doesn't match expected type."""
    
    dependency_violations: List[tuple] = field(default_factory=list)
    """List of (field, missing_dependency) tuples for unmet dependencies."""
    
    warnings: List[str] = field(default_factory=list)
    """Non-fatal issues that should be reviewed."""
    
    matched_fields: Set[str] = field(default_factory=set)
    """Fields that successfully matched and passed validation."""
    
    def summary(self) -> str:
        """Generate human-readable summary of compatibility check."""
        lines = [f"Template: {self.template_id}"]
        lines.append(f"Status: {'✓ Compatible' if self.compatible else '✗ Incompatible'}")
        
        if self.missing_fields:
            lines.append(f"Missing Required Fields: {', '.join(sorted(self.missing_fields))}")
        
        if self.extra_fields:
            lines.append(f"Extra Fields: {', '.join(sorted(self.extra_fields))}")
        
        if self.unmapped_fields:
            lines.append(f"Unmapped Fields: {', '.join(sorted(self.unmapped_fields))}")
        
        if self.type_mismatches:
            for field_name, issue in self.type_mismatches.items():
                lines.append(f"Type Mismatch in {field_name}: {issue}")
        
        if self.dependency_violations:
            for field_name, missing_dep in self.dependency_violations:
                lines.append(f"Dependency Violation: {field_name} requires {missing_dep}")
        
        if self.warnings:
            for warning in self.warnings:
                lines.append(f"⚠ Warning: {warning}")
        
        lines.append(f"Matched Fields: {len(self.matched_fields)}")
        
        return "\n".join(lines)


class TemplateRegistry:
    """Registry for managing multiple template schemas organized by family."""
    
    def __init__(self):
        """Initialize empty template registry."""
        self._templates: Dict[str, TemplateSchema] = {}
        self._families: Dict[str, List[str]] = {}
    
    def register_template(self, schema: TemplateSchema) -> None:
        """Register a new template schema.
        
        Args:
            schema: TemplateSchema to register.
            
        Raises:
            ValueError: If template_id already registered.
        """
        if schema.template_id in self._templates:
            raise ValueError(f"Template {schema.template_id} already registered")
        
        self._templates[schema.template_id] = schema
        
        # Track by family
        if schema.family not in self._families:
            self._families[schema.family] = []
        self._families[schema.family].append(schema.template_id)
    
    def get_template(self, template_id: str) -> Optional[TemplateSchema]:
        """Get a template schema by ID.
        
        Args:
            template_id: ID of the template.
            
        Returns:
            TemplateSchema if found, None otherwise.
        """
        return self._templates.get(template_id)
    
    def get_templates_by_family(self, family: str) -> List[TemplateSchema]:
        """Get all templates in a specific family.
        
        Args:
            family: Family name to retrieve.
            
        Returns:
            List of TemplateSchema objects in the family.
        """
        template_ids = self._families.get(family, [])
        return [self._templates[tid] for tid in template_ids]
    
    def list_families(self) -> List[str]:
        """Get all template families in the registry.
        
        Returns:
            Sorted list of family names.
        """
        return sorted(self._families.keys())
    
    def list_templates(self) -> List[TemplateSchema]:
        """Get all registered templates.
        
        Returns:
            List of all TemplateSchema objects.
        """
        return list(self._templates.values())
    
    def update_template(self, schema: TemplateSchema) -> None:
        """Update an existing template schema.
        
        Args:
            schema: Updated TemplateSchema.
            
        Raises:
            ValueError: If template_id not found.
        """
        if schema.template_id not in self._templates:
            raise ValueError(f"Template {schema.template_id} not found")
        
        old_family = self._templates[schema.template_id].family
        
        # Update template
        self._templates[schema.template_id] = schema
        
        # Update family tracking if family changed
        if old_family != schema.family:
            self._families[old_family].remove(schema.template_id)
            if not self._families[old_family]:
                del self._families[old_family]
            
            if schema.family not in self._families:
                self._families[schema.family] = []
            self._families[schema.family].append(schema.template_id)
    
    def delete_template(self, template_id: str) -> None:
        """Delete a template from the registry.
        
        Args:
            template_id: ID of template to delete.
            
        Raises:
            ValueError: If template_id not found.
        """
        if template_id not in self._templates:
            raise ValueError(f"Template {template_id} not found")
        
        schema = self._templates[template_id]
        
        # Remove from templates
        del self._templates[template_id]
        
        # Remove from families
        self._families[schema.family].remove(template_id)
        if not self._families[schema.family]:
            del self._families[schema.family]
