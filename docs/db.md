# Database and API Management Guide

This guide explains how to set up, initialize, and manage the FireForm database and API server.

## Prerequisites

> [!IMPORTANT]
> Ensure you have installed all dependencies before proceeding:
>
> ```bash
> pip install -r requirements.txt
> ```

## Database Setup

To create the database file and initialize the tables, run the following command from the project root:

```bash
python -m api.db.init_db
```

> [!TIP]
> After running this, you should see a `fireform.db` file in the root of the project. If you don't see it, it means the database was not successfully created.

## Running the API

Once the database is initialized, start the FastAPI server:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

If successful, you will see:
`INFO: Uvicorn running on http://127.0.0.1:8000`

## API Endpoints

The API provides the following endpoints:

### Templates

- `POST /templates/create` - Create a new PDF template
- `GET /templates/{template_id}` - Get template details

### Forms

- `POST /forms/fill` - Fill a form using AI extraction
- `GET /forms/{form_id}` - Get form details

## Testing Endpoints

1. Open your browser and go to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
2. Use the **Swagger UI** to test endpoints like `POST /templates/create`.
3. Click **"Try it out"**, fill in the data, and click **"Execute"** to see the response.

### Example Template Creation

```json
{
  "name": "Incident Report",
  "pdf_path": "src/inputs/file.pdf",
  "fields": {
    "officer_name": "string",
    "incident_date": "string",
    "location": "string"
  }
}
```

### Example Form Filling

```json
{
  "template_id": 1,
  "input_text": "Officer John Smith responded to an incident on March 22, 2026 at 123 Main Street."
}
```

## Security Features

The API includes comprehensive security validation:

- Input sanitization and validation
- XSS attack prevention
- Path traversal protection
- Prompt injection defense
- Malicious content detection

## Database Visualization

> [!NOTE]
> The database file is excluded from Git to avoid conflicts between developers.

To visualize the database:

1. Install the **SQLite3 Editor** extension in VS Code.
2. Open the `fireform.db` file directly.

## Testing

Run the test suite to verify API functionality:

```bash
pytest tests/ -v
```

The system includes comprehensive testing for all endpoints and security features.
