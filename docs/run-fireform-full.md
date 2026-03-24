# FireForm full run and testing guide (Windows local + Docker)

This repository includes:
1. API UI in FastAPI Swagger at http://localhost:8000/docs
2. Admin dashboard (SQLAdmin) at http://localhost:8000/admin

## 1) Run locally (without Docker)

Use this when you want direct local development on Windows.

```powershell
cd D:\GSOC\FireForm

# Create and activate virtual env (first time)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies (first time and whenever requirements.txt changes)
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start Ollama in a separate terminal:

```powershell
ollama serve
```

Pull the model once:

```powershell
ollama pull mistral
```

Set local env vars in your app terminal:

```powershell
$env:PYTHONPATH = "D:\GSOC\FireForm\src"
$env:OLLAMA_HOST = "http://localhost:11434"
```

Initialize DB and start API:

```powershell
python -m api.db.init_db
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Then open:
1. http://localhost:8000/docs
2. http://localhost:8000/admin
3. Login with default credentials: `admin` / `admin`

Optional: set admin credentials via environment variables before starting uvicorn:

```powershell
$env:FIREFORM_ADMIN_USER = "your_admin_user"
$env:FIREFORM_ADMIN_PASSWORD = "your_strong_password"
```

### Common local error

If you see `ModuleNotFoundError: No module named 'sqlmodel'`, run:

```powershell
pip install -r requirements.txt
```

If needed, confirm interpreter path:

```powershell
python -c "import sys; print(sys.executable)"
```

## 2) Run with Docker (automated)

The Docker setup exposes port 8000 from the app container to your machine.

```powershell
cd D:\GSOC\FireForm
powershell -ExecutionPolicy Bypass -File .\scripts\run_fireform.ps1
```

Optional first full build + smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_fireform.ps1 -Build -SmokeTest
```

## 3) Docker code-change guide (when to rebuild)

You do not need to rebuild on every code change.

No rebuild needed:
1. Changes in Python source files under `api/` or `src/`
2. Changes in templates/docs/scripts
3. Most day-to-day development edits

Use:

```powershell
docker compose up -d
```

Rebuild required:
1. `requirements.txt` changed
2. `Dockerfile` changed
3. OS/system package requirements changed

Use:

```powershell
docker compose build
docker compose up -d
```

If compose service config changed (ports, env vars, volumes), recreate services:

```powershell
docker compose up -d --force-recreate
```

If things get inconsistent, do a clean rebuild:

```powershell
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

## 4) Dashboard simulation and PDF viewer

Inside the admin dashboard:
1. Open `/admin/simulation`
2. Pick a template and submit transcript text
3. A real submission is created and appears in Form submissions
4. Open `/admin/pdf-browser` and use Open Viewer for a clean embedded PDF reader
5. Use the `Toggle Theme` button in these pages to switch between light and dark mode (theme persists in browser storage)

## 5) Admin workflow guide (templates, simulation, submissions)

Use this flow for day-to-day manual testing in the dashboard.

### A) Create a template

1. Open `http://localhost:8000/admin`
2. Sign in with your admin credentials
3. In sidebar, open `Templates`
4. Click `Create Template`
5. Fill:
  - `Name`: human-readable template name
  - `PDF Path`: relative path such as `./src/inputs/file_template.pdf`
  - `Fields`: JSON map of PDF field IDs to empty values
6. Save and verify the new template appears in the templates list

Minimal `Fields` JSON example:

```json
{
  "textbox_0_0": "",
  "textbox_0_1": "",
  "textbox_0_2": "",
  "textbox_0_3": "",
  "textbox_0_4": "",
  "textbox_0_5": "",
  "textbox_0_6": ""
}
```

### B) Run a simulation

1. Open `http://localhost:8000/admin/simulation`
2. Select the template you created
3. Paste narrative text in `Incident Transcript`
4. Click `Run Simulation`
5. Confirm success message:
  - simulation completed
  - a new submission ID was created

### C) Review submissions and generated PDFs

1. Open `Submissions` from sidebar (`/admin/form-submission/list`) to see rows created by simulation/API
2. Open `http://localhost:8000/admin/pdf-browser` for a focused PDF output list
3. Click `Open Viewer` on any row
4. In the viewer page, use:
  - embedded preview iframe
  - `Open Raw PDF` link (new tab)

If viewer shows an error:
1. Confirm the submission exists in `Submissions`
2. Confirm `output_pdf_path` file exists on disk
3. Re-run simulation if the path points to a deleted/moved file

### D) Recommended testing cycle

1. Create or edit template
2. Run simulation with known input
3. Validate output in PDF viewer
4. Verify submission metadata in `Submissions`
5. Repeat with edge-case transcripts

## 6) API testing in Swagger UI

Use these endpoints in order:
1. `POST /templates/create`
2. `POST /forms/fill`

Tip: if `template_id` is not 1 on your machine, use the ID returned by `POST /templates/create`.

Suggested `POST /templates/create` payload:

```json
{
  "name": "Test Template",
  "pdf_path": "./src/inputs/file.pdf",
  "fields": {
    "textbox_0_0": "",
    "textbox_0_1": "",
    "textbox_0_2": "",
    "textbox_0_3": "",
    "textbox_0_4": "",
    "textbox_0_5": "",
    "textbox_0_6": ""
  }
}
```

Suggested `POST /forms/fill` payload:

```json
{
  "template_id": 1,
  "input_text": "Hi. The employee name is John Doe. Job title is managing director. Department supervisor is Jane Doe. Phone is 123456. Email is jdoe@ucsc.edu. Signature is John Doe. Date is 01/02/2005."
}
```
