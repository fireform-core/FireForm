# Department Profiles - Quick Reference

## What Are Department Profiles?

Pre-built field mappings that translate machine-generated PDF field names (like `textbox_0_0`) into human-readable labels (like `Officer Name`) so the LLM can accurately extract information.

## The Problem They Solve

**Without Profiles:**
```
PDF Field: textbox_0_0
LLM: "What is textbox_0_0? I have no idea."
Result: null or hallucinated values
```

**With Profiles:**
```
PDF Field: textbox_0_0 → "Officer Name"
LLM: "Extract the officer's name from the transcript."
Result: Accurate extraction
```

## Available Profiles

| Profile Name | Department | Use For |
|-------------|------------|---------|
| `fire_department` | Fire Department | Cal Fire incident reports, structure fires, wildland fires |
| `police_report` | Police Department | Criminal incidents, traffic accidents, public safety events |
| `ems_medical` | Emergency Medical Services | Medical emergencies, trauma incidents, patient transport |

## Quick Start

### Python API

```python
from src.controller import Controller

controller = Controller()

# Use a profile
output = controller.fill_form(
    user_input="Officer Smith, badge 4421, responding to fire...",
    fields={},
    pdf_form_path="fire_report.pdf",
    profile_name="fire_department"  # ← Add this
)
```

### REST API

```bash
# List profiles
curl http://localhost:8000/profiles/

# Get profile details
curl http://localhost:8000/profiles/fire_department

# Fill form with profile
curl -X POST http://localhost:8000/forms/fill \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "input_text": "Officer Smith, badge 4421...",
    "profile_name": "fire_department"
  }'
```

## Profile Fields

### Fire Department (15 fields)
- Officer Name, Badge Number
- Incident Location, Date, Time
- Number of Victims, Victim Names
- Incident Type, Fire Cause
- Property Damage Estimate
- Number of Units Responding, Response Time
- Incident Description, Actions Taken, Additional Notes

### Police Report (15 fields)
- Officer Name, Badge Number
- Incident Location, Date, Time
- Case Number, Incident Type
- Suspect Name, Suspect Description
- Victim Name, Witness Names
- Property Involved, Evidence Collected
- Incident Narrative, Follow-up Required

### EMS Medical (15 fields)
- Paramedic Name, Certification Number
- Incident Location, Call Date, Call Time
- Patient Name, Age, Gender
- Chief Complaint, Vital Signs
- Medical History, Medications
- Treatment Provided, Transport Destination, Patient Condition

## When to Use Profiles

✅ **Use profiles when:**
- Filling standard Fire/Police/EMS forms
- You want accurate extraction immediately
- The form matches a profile structure

❌ **Don't use profiles when:**
- Using custom department forms
- Fields don't match profile
- You need custom mappings

## Creating Custom Profiles

1. Create `src/profiles/your_profile.json`:

```json
{
  "department": "Your Department",
  "description": "Form description",
  "fields": {
    "Human Label": "textbox_0_0",
    "Another Field": "textbox_0_1"
  },
  "example_transcript": "Example text..."
}
```

2. Profile is automatically available via API

## Testing

```bash
# Run profile tests
python3 test_profiles_simple.py

# View examples
python3 examples/profile_usage_example.py
```

## Benefits

1. ✅ **Accurate Extraction** - LLM understands field context
2. ✅ **No Null Values** - Proper labels enable correct extraction
3. ✅ **No Hallucination** - Each field gets appropriate value
4. ✅ **Works Out-of-Box** - No setup required for common forms
5. ✅ **Solves Issue #173** - Fixes PDF filler hallucination bug

## Related Documentation

- Full documentation: `docs/profiles.md`
- Usage examples: `examples/profile_usage_example.py`
- Tests: `tests/test_profiles.py`
- Related issue: #173 (PDF filler hallucination)
- Related feature: #111 (Field Mapping Wizard for custom forms)
