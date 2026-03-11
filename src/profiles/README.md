# Department Profiles

This directory contains pre-built field mappings for common first responder forms.

## Purpose

PDF forms use machine-generated field identifiers (e.g., `textbox_0_0`) that provide no semantic context to the LLM. Department profiles map these identifiers to human-readable labels (e.g., "Officer Name"), enabling accurate information extraction.

## Available Profiles

### fire_department.json
Standard Cal Fire incident report form
- 15 fields covering officer info, incident details, victims, damage assessment
- Use for: Structure fires, wildland fires, emergency responses

### police_report.json
Standard police incident report form
- 15 fields covering officer info, case details, suspects, victims, evidence
- Use for: Criminal incidents, traffic accidents, public safety events

### ems_medical.json
EMS patient care report form
- 15 fields covering paramedic info, patient details, vitals, treatment
- Use for: Medical emergencies, trauma incidents, patient transport

## Profile Schema

Each profile follows this structure:

```json
{
  "department": "Department Name",
  "description": "Form description and use cases",
  "fields": {
    "Human Readable Label": "pdf_field_identifier",
    ...
  },
  "example_transcript": "Sample voice transcript for this form type"
}
```

## Usage

### Python
```python
from src.profiles import ProfileLoader

# List profiles
profiles = ProfileLoader.list_profiles()

# Load a profile
profile = ProfileLoader.load_profile('fire_department')

# Get field mapping
mapping = ProfileLoader.get_field_mapping('fire_department')
```

### API
```bash
# List profiles
GET /profiles/

# Get profile details
GET /profiles/fire_department

# Use in form filling
POST /forms/fill
{
  "template_id": 1,
  "input_text": "...",
  "profile_name": "fire_department"
}
```

## Creating Custom Profiles

1. Create a new JSON file in this directory (e.g., `sheriff_report.json`)
2. Follow the schema structure above
3. Map human-readable labels to PDF field identifiers
4. Include an example transcript
5. Profile is automatically available via ProfileLoader

## Field Identifier Format

Field identifiers typically follow patterns like:
- `textbox_0_0`, `textbox_0_1`, etc. (indexed text boxes)
- `checkbox_1_0`, `checkbox_1_1`, etc. (indexed checkboxes)
- Custom identifiers from PDF form structure

To find field identifiers in your PDF:
```python
from pypdf import PdfReader

reader = PdfReader("your_form.pdf")
fields = reader.get_fields()
for name, field in fields.items():
    print(f"{name}: {field}")
```

## Testing

Test profiles using:
```bash
# Run profile tests
PYTHONPATH=. python3 tests/test_profiles_simple.py

# View examples
PYTHONPATH=. python3 examples/profile_usage_example.py
```

## Documentation

- Full documentation: `docs/profiles.md`
- Quick reference: `docs/profiles_quick_reference.md`
- Migration guide: `docs/profiles_migration_guide.md`

## Benefits

1. Accurate LLM extraction with semantic context
2. No null values or hallucinated data
3. Works out-of-the-box for common forms
4. Easy to extend with custom profiles
5. Solves Issue #173 (PDF filler hallucination)
