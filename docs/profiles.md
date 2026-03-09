# Department Profile System

## Overview

The Department Profile System provides pre-built field mappings for common first responder forms used by Fire Departments, Police, and EMS. This solves the core issue where PDF field names are machine-generated identifiers (e.g., `textbox_0_0`) that provide no semantic context to the LLM, resulting in null values or hallucinated data.

## Problem Statement

FireForm extracts PDF field names as identifiers like:
- `textbox_0_0`
- `textbox_0_1`
- `textbox_0_2`

When Mistral receives these field names, it has no idea what information to extract, leading to:
- Null values for all fields
- Hallucinated data (same value repeated across unrelated fields)
- Blank or incorrect filled PDFs

## Solution

Department profiles map human-readable labels to PDF field identifiers:

```json
{
  "Officer Name": "textbox_0_0",
  "Badge Number": "textbox_0_1",
  "Incident Location": "textbox_0_2"
}
```

Now Mistral receives meaningful field names and can accurately extract the correct information from transcripts.

## Available Profiles

### 1. Fire Department (`fire_department`)
Standard Cal Fire incident report for structure fires, wildland fires, and emergency responses.

**Fields:**
- Officer Name
- Badge Number
- Incident Location
- Incident Date
- Incident Time
- Number of Victims
- Victim Names
- Incident Type
- Fire Cause
- Property Damage Estimate
- Number of Units Responding
- Response Time
- Incident Description
- Actions Taken
- Additional Notes

### 2. Police Report (`police_report`)
Standard police incident report for criminal incidents, traffic accidents, and public safety events.

**Fields:**
- Officer Name
- Badge Number
- Incident Location
- Incident Date
- Incident Time
- Case Number
- Incident Type
- Suspect Name
- Suspect Description
- Victim Name
- Witness Names
- Property Involved
- Evidence Collected
- Incident Narrative
- Follow-up Required

### 3. EMS Medical (`ems_medical`)
EMS patient care report for medical emergencies, trauma incidents, and patient transport.

**Fields:**
- Paramedic Name
- Certification Number
- Incident Location
- Call Date
- Call Time
- Patient Name
- Patient Age
- Patient Gender
- Chief Complaint
- Vital Signs
- Medical History
- Medications
- Treatment Provided
- Transport Destination
- Patient Condition

## Usage

### API Usage

#### List Available Profiles
```bash
GET /profiles/
```

Response:
```json
["ems_medical", "fire_department", "police_report"]
```

#### Get Profile Details
```bash
GET /profiles/fire_department
```

Response:
```json
{
  "department": "Fire Department",
  "description": "Standard Cal Fire incident report...",
  "fields": {
    "Officer Name": "textbox_0_0",
    "Badge Number": "textbox_0_1",
    ...
  },
  "example_transcript": "Officer Smith, badge 4421..."
}
```

#### Fill Form with Profile
```bash
POST /forms/fill
Content-Type: application/json

{
  "template_id": 1,
  "input_text": "Officer Smith, badge 4421, responding to structure fire...",
  "profile_name": "fire_department"
}
```

### Python Usage

```python
from src.profiles import ProfileLoader
from src.controller import Controller

# List available profiles
profiles = ProfileLoader.list_profiles()
print(profiles)  # ['ems_medical', 'fire_department', 'police_report']

# Load a profile
profile = ProfileLoader.load_profile('fire_department')
print(profile['department'])  # "Fire Department"

# Use profile when filling a form
controller = Controller()
output_path = controller.fill_form(
    user_input="Officer Smith, badge 4421...",
    fields={},  # Can be empty when using profile
    pdf_form_path="path/to/form.pdf",
    profile_name="fire_department"
)
```

## Profile Schema

Each profile JSON file follows this schema:

```json
{
  "department": "string - Department name",
  "description": "string - Description of the form type",
  "fields": {
    "Human Readable Label": "pdf_field_identifier",
    ...
  },
  "example_transcript": "string - Example voice transcript for this form type"
}
```

## Creating Custom Profiles

To create a new department profile:

1. Create a new JSON file in `src/profiles/` (e.g., `sheriff_report.json`)

2. Follow the profile schema:
```json
{
  "department": "Sheriff Department",
  "description": "County sheriff incident report",
  "fields": {
    "Deputy Name": "textbox_0_0",
    "Badge Number": "textbox_0_1",
    "County": "textbox_0_2"
  },
  "example_transcript": "Deputy Johnson, badge 5512..."
}
```

3. The profile will automatically be available via the API

## Benefits

1. **Improved Accuracy**: LLM receives semantic field names instead of generic identifiers
2. **No Null Values**: Proper field context enables correct extraction
3. **No Hallucination**: Each field gets its appropriate value, not repeated data
4. **Out-of-the-Box**: First responders can use FireForm immediately without setup
5. **Standardization**: Common forms work consistently across departments

## Related Features

- **Issue #173**: This directly solves the PDF filler hallucination bug
- **Issue #111**: Field Mapping Wizard complements this for custom PDFs not covered by profiles

## Docker Support

Profiles are included in the Docker container and work without additional configuration:

```bash
docker-compose up
# Profiles are automatically available at /profiles/ endpoint
```

## Testing

Test profile functionality:

```python
# Test profile loading
from src.profiles import ProfileLoader

profiles = ProfileLoader.list_profiles()
assert 'fire_department' in profiles
assert 'police_report' in profiles
assert 'ems_medical' in profiles

# Test field mapping
mapping = ProfileLoader.get_field_mapping('fire_department')
assert 'Officer Name' in mapping
assert 'Badge Number' in mapping
```

## Future Enhancements

- Additional department profiles (Sheriff, Coast Guard, etc.)
- Profile versioning for form updates
- Custom profile upload via UI
- Profile validation and testing tools
- Multi-language profile support
