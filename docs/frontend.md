# Frontend UI Guide

This guide explains how to set up and use the FireForm browser-based frontend interface.

## Overview

The FireForm frontend is a single-page web application (`frontend/index.html`) that provides a user-friendly interface for non-technical first responders to:

- Upload and save fillable PDF form templates
- Describe incidents in plain language
- Auto-fill forms using local AI (Mistral via Ollama)
- Download completed PDF forms instantly

> [!IMPORTANT]
> The frontend communicates with the FastAPI backend at `http://127.0.0.1:8000`. Make sure both Ollama and the API server are running before opening the frontend.

---

## Prerequisites

Before running the frontend, ensure the following are set up:

> [!IMPORTANT]
> Complete the database setup described in [db.md](db.md) first.

1. **Ollama** installed and running — [https://ollama.com/download](https://ollama.com/download)
2. **Mistral model** pulled:
   ```bash
   ollama pull mistral
   ```
3. **Dependencies** installed:
   ```bash
   pip install -r requirements.txt
   ```

---

## Running the Frontend

### Step 1 — Start Ollama

In a terminal, run:

```bash
ollama serve
```

> [!TIP]
> Leave this terminal open. Ollama must stay running for AI extraction to work.

### Step 2 — Initialize the Database

```bash
python -m api.db.init_db
```

### Step 3 — Start the API Server

In a new terminal, from the project root:

```bash
uvicorn api.main:app --reload
```

If successful, you will see:
`INFO: Uvicorn running on http://127.0.0.1:8000`

### Step 4 — Open the Frontend

Open `frontend/index.html` directly in your browser by double-clicking it, or navigate to it in your file explorer.

> [!NOTE]
> No additional server is required for the frontend. It is a static HTML file that communicates directly with the FastAPI backend.

---

## Using the Frontend

The interface guides you through 4 steps:

### Step 1 — Upload a Template

1. Click **"Click to upload"** or drag and drop a fillable PDF form
2. Enter a name for the template (e.g. `Cal Fire Incident Report`)
3. Click **"SAVE TEMPLATE →"**

The template is saved to the database and will appear in the **Saved Templates** list.

> [!TIP]
> Any fillable PDF form works. The system automatically detects all form fields.

### Step 2 — Select a Template

Click any saved template from the **Saved Templates** list in the sidebar. The selected template will be highlighted in red.

### Step 3 — Describe the Incident

Type or paste a plain-language description of the incident in the text area. For best results, include all relevant details that match your form's fields.

**Example for an employee form:**
```
The employee's name is John Smith. His employee ID is EMP-2024-789.
His job title is Firefighter Paramedic. His location is Station 12,
Sacramento. His department is Emergency Medical Services. His supervisor
is Captain Jane Rodriguez. His phone number is 916-555-0147.
His email is jsmith@calfire.ca.gov.
```

**Example for an incident report form:**
```
Officer Hernandez responding to a structure fire at 742 Evergreen Terrace.
Two occupants evacuated safely. Minor smoke inhalation treated on scene
by EMS. Unit 7 on scene at 14:32, cleared at 16:45.
Handed off to Deputy Martinez.
```

### Step 4 — Fill and Download

Click **"⚡ FILL FORM"**. The system will:

1. Send the description to Mistral (running locally via Ollama)
2. Extract all relevant field values
3. Fill the PDF template automatically
4. Provide a **"⬇ Download PDF"** button

> [!NOTE]
> Processing time depends on your hardware. Typically 10–30 seconds with Mistral on a standard machine.

---

## API Endpoints

The frontend uses the following API endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/templates/create` | Upload a new PDF template |
| `GET` | `/templates` | List all saved templates |
| `GET` | `/templates/{id}` | Get a specific template |
| `POST` | `/forms/fill` | Fill a form with incident text |
| `GET` | `/forms/{id}` | Get a submission record |
| `GET` | `/forms/download/{id}` | Download a filled PDF |

For full API documentation, visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) while the server is running.

---

## API Status Indicator

The top-right corner of the frontend shows the API connection status:

- 🟢 **api online** — Backend is reachable, ready to use
- 🔴 **api offline** — Backend is not running, check uvicorn

---

## Troubleshooting

### "api offline" shown in the top bar

The FastAPI server is not running. Start it with:
```bash
uvicorn api.main:app --reload
```

### Form fills with null or incorrect values

This happens when the incident description does not contain information matching the PDF form fields. Ensure your description includes the specific data your form requires (names, dates, locations, etc.).

See [Issue #113](https://github.com/fireform-core/FireForm/issues/113) for context on matching input to templates.

### "Could not connect to Ollama" error

Ollama is not running. Start it with:
```bash
ollama serve
```

Then verify Mistral is available:
```bash
ollama list
```

If Mistral is not listed, pull it:
```bash
ollama pull mistral
```

### Port conflict on 11434

Something else is using Ollama's port. On Linux/Mac:
```bash
sudo lsof -i :11434
```
On Windows:
```cmd
netstat -ano | findstr :11434
```

---

## Privacy

> [!IMPORTANT]
> FireForm is designed to be fully private. All AI processing happens locally via Ollama. No incident data, form content, or personal information is ever sent to external servers.

---

## Docker Usage

To run the full stack including the frontend API via Docker:

```bash
chmod +x container-init.sh
./container-init.sh
```

See [docker.md](docker.md) for full Docker setup instructions.
