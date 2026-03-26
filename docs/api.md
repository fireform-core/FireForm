# FireForm API Documentation

## Overview

The FireForm API provides endpoints for creating PDF templates and filling forms using AI-powered text extraction. The API is built with FastAPI and includes comprehensive security validation.

## Base URL

```
http://127.0.0.1:8000
```

## Authentication

Currently, the API does not require authentication. This is suitable for local deployment and development.

## Endpoints

### Templates

#### Create Template

Create a new PDF template for form filling.

**Endpoint**: `POST /templates/create`

**Request Body**:

```json
{
  "name": "string",
  "pdf_path": "string",
  "fields": {
    "field_name": "field_type"
  }
}
```

**Parameters**:

- `name` (string, required): Human-readable name for the template
- `pdf_path` (string, required): Path to the PDF template file
- `fields` (object, required): Mapping of field names to their types

**Example Request**:

```json
{
  "name": "Incident Report Template",
  "pdf_path": "src/inputs/incident_report.pdf",
  "fields": {
    "officer_name": "string",
    "incident_date": "string",
    "location": "string",
    "description": "string"
  }
}
```

**Response**:

```json
{
  "id": 1,
  "name": "Incident Report Template",
  "pdf_path": "src/inputs/incident_report.pdf",
  "fields": {
    "officer_name": "string",
    "incident_date": "string",
    "location": "string",
    "description": "string"
  }
}
```

#### Get Template

Retrieve details of a specific template.

**Endpoint**: `GET /templates/{template_id}`

**Parameters**:

- `template_id` (integer, required): ID of the template

**Response**:

```json
{
  "id": 1,
  "name": "Incident Report Template",
  "pdf_path": "src/inputs/incident_report.pdf",
  "fields": {
    "officer_name": "string",
    "incident_date": "string",
    "location": "string",
    "description": "string"
  }
}
```

### Forms

#### Fill Form

Fill a PDF form using AI extraction from natural language input.

**Endpoint**: `POST /forms/fill`

**Request Body**:

```json
{
  "template_id": "integer",
  "input_text": "string"
}
```

**Parameters**:

- `template_id` (integer, required): ID of the template to use
- `input_text` (string, required): Natural language description of the incident

**Example Request**:

```json
{
  "template_id": 1,
  "input_text": "Officer John Smith responded to a vehicle accident on March 22, 2026 at the intersection of Main Street and Oak Avenue. The incident involved two vehicles with minor injuries reported."
}
```

**Response**:

```json
{
  "id": 1,
  "template_id": 1,
  "input_text": "Officer John Smith responded to a vehicle accident...",
  "output_pdf_path": "incident_report_abc123_filled.pdf"
}
```

#### Get Form

Retrieve details of a specific filled form.

**Endpoint**: `GET /forms/{form_id}`

**Parameters**:

- `form_id` (integer, required): ID of the filled form

**Response**:

```json
{
  "id": 1,
  "template_id": 1,
  "input_text": "Officer John Smith responded to a vehicle accident...",
  "output_pdf_path": "incident_report_abc123_filled.pdf"
}
```

## Error Responses

### Validation Error (422)

Returned when request data fails validation.

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Not Found (404)

Returned when a requested resource doesn't exist.

```json
{
  "detail": "Template not found"
}
```

### Internal Server Error (500)

Returned when an unexpected error occurs.

```json
{
  "detail": "Internal server error"
}
```

## Security Features

The API includes comprehensive security validation:

### Input Validation

- **XSS Protection**: Detects and blocks script tags and malicious HTML
- **Homograph Detection**: Prevents attacks using similar-looking characters
- **Path Traversal Prevention**: Blocks attempts to access unauthorized files
- **Prompt Injection Defense**: Prevents manipulation of AI prompts

### Content Sanitization

- HTML entity decoding with safety checks
- Unicode normalization to prevent encoding attacks
- URL decoding validation
- Malicious content pattern detection

### Error Handling

- Sanitized error messages to prevent information leakage
- Proper HTTP status codes
- Comprehensive logging for debugging

## Rate Limiting

Currently, no rate limiting is implemented. For production deployment, consider implementing rate limiting based on your requirements.

## Interactive Documentation

The API provides interactive documentation via Swagger UI:

- **Swagger UI**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`

## Testing

Test the API endpoints using the provided test suite:

```bash
pytest tests/ -v
```

Or use curl for manual testing:

```bash
# Create a template
curl -X POST "http://127.0.0.1:8000/templates/create" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Template",
    "pdf_path": "src/inputs/file.pdf",
    "fields": {"name": "string", "date": "string"}
  }'

# Fill a form
curl -X POST "http://127.0.0.1:8000/forms/fill" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "input_text": "John Smith submitted the form on March 22, 2026"
  }'
```

## Development

To start the development server:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

The `--reload` flag enables automatic reloading when code changes are detected.
