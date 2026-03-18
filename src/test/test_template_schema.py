"""Tests for template schema registry and compatibility checking."""

import pytest
from src.template_schema import (
    FieldSchema,
    FieldType,
    TemplateSchema,
    TemplateRegistry,
    CompatibilityReport,
)
from src.compatibility_checker import CompatibilityChecker


@pytest.fixture
def registry():
    """Create a template registry with sample templates."""
    reg = TemplateRegistry()
    
    # Template 1: Employment Form
    employment_schema = TemplateSchema(
        template_id="emp-form-v1",
        template_name="Employment Application",
        version="1.0.0",
        family="employment",
        description="Standard employment application form",
        fields={
            "employee_name": FieldSchema(
                name="employee_name",
                field_type=FieldType.TEXT,
                required=True,
                aliases=["full_name", "applicant_name"],
                max_length=100,
            ),
            "email": FieldSchema(
                name="email",
                field_type=FieldType.EMAIL,
                required=True,
                aliases=["email_address", "contact_email"],
            ),
            "phone": FieldSchema(
                name="phone",
                field_type=FieldType.PHONE,
                required=True,
                aliases=["phone_number", "contact_phone"],
            ),
            "position": FieldSchema(
                name="position",
                field_type=FieldType.TEXT,
                required=True,
                aliases=["job_title"],
            ),
            "start_date": FieldSchema(
                name="start_date",
                field_type=FieldType.DATE,
                required=False,
                aliases=["employment_start"],
            ),
            "years_experience": FieldSchema(
                name="years_experience",
                field_type=FieldType.NUMBER,
                required=False,
                aliases=["experience_years"],
            ),
        },
    )
    reg.register_template(employment_schema)
    
    # Template 2: Medical Form
    medical_schema = TemplateSchema(
        template_id="med-form-v1",
        template_name="Medical History",
        version="1.0.0",
        family="medical",
        description="Patient medical history form",
        fields={
            "patient_name": FieldSchema(
                name="patient_name",
                field_type=FieldType.TEXT,
                required=True,
                aliases=["full_name"],
            ),
            "date_of_birth": FieldSchema(
                name="date_of_birth",
                field_type=FieldType.DATE,
                required=True,
                aliases=["birthdate", "dob"],
            ),
            "allergies": FieldSchema(
                name="allergies",
                field_type=FieldType.TEXT,
                required=False,
            ),
        },
    )
    reg.register_template(medical_schema)
    
    return reg


def test_template_registration(registry):
    """Test that templates are properly registered in the registry."""
    assert len(registry.list_templates()) == 2
    assert registry.get_template("emp-form-v1") is not None
    assert registry.get_template("med-form-v1") is not None
    assert registry.get_template("nonexistent") is None


def test_template_family_grouping(registry):
    """Test that templates are grouped by family correctly."""
    employment_templates = registry.get_templates_by_family("employment")
    assert len(employment_templates) == 1
    assert employment_templates[0].template_id == "emp-form-v1"
    
    medical_templates = registry.get_templates_by_family("medical")
    assert len(medical_templates) == 1
    assert medical_templates[0].template_id == "med-form-v1"


def test_template_families_listing(registry):
    """Test listing all template families."""
    families = registry.list_families()
    assert "employment" in families
    assert "medical" in families


def test_field_name_resolution(registry):
    """Test resolving extracted field names to canonical names."""
    template = registry.get_template("emp-form-v1")
    
    # Exact match
    assert template.resolve_field_name("employee_name") == "employee_name"
    
    # Alias match
    assert template.resolve_field_name("full_name") == "employee_name"
    assert template.resolve_field_name("applicant_name") == "employee_name"
    
    # Non-match
    assert template.resolve_field_name("nonexistent_field") is None


def test_compatibility_check_valid_data(registry):
    """Test that valid extracted data passes compatibility check."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-1234567",
        "position": "Software Engineer",
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert report.compatible
    assert len(report.missing_fields) == 0
    assert len(report.extra_fields) == 0


def test_compatibility_check_missing_required_fields(registry):
    """Test that missing required fields trigger incompatibility."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        # Missing required: email, phone, position
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert not report.compatible
    assert "email" in report.missing_fields
    assert "phone" in report.missing_fields
    assert "position" in report.missing_fields


def test_compatibility_check_extra_fields(registry):
    """Test that extra fields not in template are reported."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-1234567",
        "position": "Software Engineer",
        "salary": "100000",  # Extra field
        "department": "Engineering",  # Extra field
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert not report.compatible
    assert "salary" in report.extra_fields
    assert "department" in report.extra_fields


def test_compatibility_check_with_aliases(registry):
    """Test that aliased field names are correctly mapped."""
    checker = CompatibilityChecker(registry)
    
    # Using aliases instead of canonical names
    extracted_data = {
        "full_name": "John Doe",  # Alias for employee_name
        "email_address": "john@example.com",  # Alias for email
        "contact_phone": "555-1234567",  # Alias for phone
        "job_title": "Software Engineer",  # Alias for position
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert report.compatible
    assert len(report.missing_fields) == 0
    assert len(report.extra_fields) == 0


def test_compatibility_check_type_validation_email(registry):
    """Test that email field type is validated."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "invalid-email",  # Not a valid email
        "phone": "555-1234567",
        "position": "Software Engineer",
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert not report.compatible
    assert "email" in report.type_mismatches


def test_compatibility_check_type_validation_phone(registry):
    """Test that phone field type is validated."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "john@example.com",
        "phone": "123",  # Too short for valid phone
        "position": "Software Engineer",
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert not report.compatible
    assert "phone" in report.type_mismatches


def test_compatibility_check_type_validation_date(registry):
    """Test that date field type is validated."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "patient_name": "Jane Doe",
        "date_of_birth": "not-a-date",  # Invalid date format
    }
    
    report = checker.check_compatibility("med-form-v1", extracted_data)
    assert not report.compatible
    assert "date_of_birth" in report.type_mismatches


def test_compatibility_check_type_validation_date_valid_formats(registry):
    """Test that various valid date formats are accepted."""
    checker = CompatibilityChecker(registry)
    
    valid_dates = [
        "01/15/1990",
        "1990-01-15",
        "January 15, 1990",
    ]
    
    for date_value in valid_dates:
        extracted_data = {
            "patient_name": "Jane Doe",
            "date_of_birth": date_value,
        }
        
        report = checker.check_compatibility("med-form-v1", extracted_data)
        assert report.compatible, f"Date format '{date_value}' should be valid"


def test_compatibility_check_type_validation_number(registry):
    """Test that number field type is validated."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-1234567",
        "position": "Software Engineer",
        "years_experience": "not-a-number",
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert not report.compatible
    assert "years_experience" in report.type_mismatches


def test_compatibility_check_matched_fields(registry):
    """Test that successfully matched fields are tracked."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-1234567",
        "position": "Software Engineer",
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    assert len(report.matched_fields) == 4
    assert "employee_name" in report.matched_fields


def test_family_compatibility_check(registry):
    """Test checking extracted data against all templates in a family."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-1234567",
        "position": "Software Engineer",
    }
    
    reports = checker.check_family_compatibility("employment", extracted_data)
    assert len(reports) == 1
    assert "emp-form-v1" in reports
    assert reports["emp-form-v1"].compatible


def test_find_compatible_templates(registry):
    """Test finding templates compatible with extracted data."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "patient_name": "Jane Doe",
        "date_of_birth": "01/15/1990",
    }
    
    compatible = checker.find_compatible_templates(extracted_data)
    assert len(compatible) > 0
    assert compatible[0][0] == "med-form-v1"
    assert compatible[0][1].compatible


def test_compatibility_report_summary(registry):
    """Test that compatibility report generates readable summary."""
    checker = CompatibilityChecker(registry)
    
    extracted_data = {
        "employee_name": "John Doe",
        "email": "invalid-email",
        "phone": "555-1234567",
        "position": "Software Engineer",
        "extra_field": "value",
    }
    
    report = checker.check_compatibility("emp-form-v1", extracted_data)
    summary = report.summary()
    
    assert "emp-form-v1" in summary
    assert "Incompatible" in summary
    assert "email" in summary.lower()


def test_template_update(registry):
    """Test updating an existing template in the registry."""
    template = registry.get_template("emp-form-v1")
    original_version = template.version
    
    template.version = "1.1.0"
    registry.update_template(template)
    
    updated = registry.get_template("emp-form-v1")
    assert updated.version == "1.1.0"


def test_template_delete(registry):
    """Test deleting a template from the registry."""
    registry.delete_template("emp-form-v1")
    
    assert registry.get_template("emp-form-v1") is None
    assert len(registry.list_templates()) == 1


def test_template_schema_get_required_fields(registry):
    """Test getting all required fields from a template."""
    template = registry.get_template("emp-form-v1")
    required = template.get_required_fields()
    
    assert "employee_name" in required
    assert "email" in required
    assert "phone" in required
    assert "position" in required


def test_field_schema_get_all_names(registry):
    """Test getting all possible field names (primary + aliases)."""
    template = registry.get_template("emp-form-v1")
    field_schema = template.fields["employee_name"]
    
    all_names = field_schema.get_all_names()
    assert "employee_name" in all_names
    assert "full_name" in all_names
    assert "applicant_name" in all_names


def test_compatibility_check_invalid_template():
    """Test that checking against non-existent template raises error."""
    registry = TemplateRegistry()
    checker = CompatibilityChecker(registry)
    
    extracted_data = {"field": "value"}
    
    with pytest.raises(ValueError, match="not found"):
        checker.check_compatibility("nonexistent", extracted_data)


def test_duplicate_template_registration():
    """Test that registering duplicate template ID raises error."""
    registry = TemplateRegistry()
    
    schema = TemplateSchema(
        template_id="test-v1",
        template_name="Test",
        version="1.0.0",
        family="test",
    )
    
    registry.register_template(schema)
    
    with pytest.raises(ValueError, match="already registered"):
        registry.register_template(schema)
