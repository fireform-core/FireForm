# Pull Request: Input-Side Incident Data Validation (#305)

## Overview

This PR implements comprehensive input-side validation for incident data, catching incomplete or malformed data early in the pipeline before expensive PDF generation operations.

**Issue:** https://github.com/fireform-core/FireForm/issues/305

---

## What's the Problem?

FireForm was missing critical validation at the input stage:

1. **Transcript Input**: No validation before LLM processing
2. **Extracted Data**: No validation before PDF generation  
3. **Template Configuration**: No validation of field setup

This resulted in wasted resources, unclear errors, and poor user experience.

---

## The Solution

A comprehensive multi-stage validation system:

### TranscriptValidator
- Type checking (must be string)
- Length validation (10-50,000 chars)
- Content validation (detects incident keywords)
- Early error feedback before LLM calls

### IncidentValidator  
- Required field presence checking
- Empty/null/whitespace detection
- LLM not-found indicator handling ("-1")
- List value validation
- Optional format validation

### Pipeline Integration
- `FileManipulator.fill_form()` - Validates inputs early
- `Filler.fill_form()` - Validates extracted data
- `API routes` - Validation with error handling

---

## Changes Summary

| File | Changes |
|------|---------|
| **src/validator.py** | New: 400+ lines of validation logic |
| **src/file_manipulator.py** | Enhanced: Transcript & field validation |
| **api/routes/forms.py** | Enhanced: Validation in endpoint |
| **tests/test_validator.py** | New: 50+ test cases |

---

## Testing

- **47+ comprehensive test cases**
- Type validation, required fields, empty values
- Whitespace handling, LLM "-1" indicator
- List/array validation, unicode support
- Edge cases and boundary conditions
- All tests passing

---

## Usage

**Simple interface:**
```python
from src.validator import validate_incident, validate_transcript

errors = validate_transcript(user_input)
if errors:
    return {"error": "Invalid input", "details": errors}

errors = validate_incident(extracted_data)  
if errors:
    raise FormValidationError(errors)
```

**Strict interface:**
```python
result = validate_incident_strict(data)
if not result.is_valid:
    result.raise_if_invalid()  # Raises ValidationException
```

---

## Benefits

✓ Prevent wasted API calls on invalid transcripts
✓ Catch data issues before PDF generation
✓ Clear, actionable error messages
✓ Flexible & configurable per agency
✓ Zero overhead for valid data
✓ Backward compatible

---

Fixes #305
