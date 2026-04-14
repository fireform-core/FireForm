# Database and API Management Guide

This guide explains how to set up, initialize, and manage the FireForm database.

## Prerequisites

> [!IMPORTANT]
> Ensure you have installed all dependencies before proceeding:
> ```bash
> pip install -r requirements-dev.txt
> ```
>
> Install the optional AI/PDF extras only if you want template creation and the Ollama-backed fill flow:
> ```bash
> pip install -r requirements-ai.txt
> ```

## Database Setup

To create the database file and initialize the tables, run the following command from the project root:

```bash
python -m api.db.init_db
```

> [!TIP]
> After running this, you should see a `.db` file in the root of the project. If you don't see it, it means the database was not successfully created.

## Running the API

Once the database is initialized, start the FastAPI server:

```bash
uvicorn api.main:app --reload
```

If successful, you will see:
`INFO: Uvicorn running on http://127.0.0.1:8000`

## Running Tests

The package is installed in editable mode by `requirements-dev.txt`, so tests can be run from the project root without setting `PYTHONPATH` manually:

```bash
pytest -q
```

## Testing Endpoints

1. Open your browser and go to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
2. Use the **Swagger UI** to test endpoints like `POST /templates/create`.
3. Click **"Try it out"**, fill in the data, and click **"Execute"** to see the response.

## Database Visualization

> [!NOTE]
> The database file is excluded from Git to avoid conflicts between developers.

To visualize the database:
1. Install the **SQLite3 Editor** extension in VS Code.
2. Open the `.db` file directly.
