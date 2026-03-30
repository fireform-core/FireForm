# 🔥 FireForm — Setup & Usage Guide

This guide covers how to install, run, and use FireForm locally on Windows, Linux, and macOS.

---

## 📋 Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Ollama | 0.17.7+ | Local LLM server |
| Mistral 7B | latest | AI extraction model |
| Git | any | Clone the repository |

---

## 🪟 Windows

### 1. Clone the repository
```cmd
git clone https://github.com/fireform-core/FireForm.git
cd FireForm
```

### 2. Create and activate virtual environment
```cmd
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```cmd
pip install -r requirements.txt
```

### 4. Install and start Ollama
Download Ollama from https://ollama.com/download/windows

Then pull the Mistral model:
```cmd
ollama pull mistral
ollama serve
```

> Ollama runs on `http://localhost:11434` by default. Keep this terminal open.

### 5. Initialize the database
```cmd
python -m api.db.init_db
```

### 6. Start the API server
```cmd
uvicorn api.main:app --reload
```

API is now running at `http://127.0.0.1:8000`

### 7. Start the frontend
Open a new terminal:
```cmd
cd frontend
python -m http.server 3000
```

Open `http://localhost:3000` in your browser.

---

## 🐧 Linux (Ubuntu/Debian)

### 1. Clone and enter the repository
```bash
git clone https://github.com/fireform-core/FireForm.git
cd FireForm
```

### 2. Create and activate virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Install and start Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
ollama serve &
```

### 5. Initialize the database
```bash
python -m api.db.init_db
```

### 6. Start the API server
```bash
uvicorn api.main:app --reload
```

### 7. Start the frontend
```bash
cd frontend
python3 -m http.server 3000
```

---

## 🍎 macOS

### 1. Clone and enter the repository
```bash
git clone https://github.com/fireform-core/FireForm.git
cd FireForm
```

### 2. Create and activate virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Install and start Ollama
Download from https://ollama.com/download/mac or:
```bash
brew install ollama
ollama pull mistral
ollama serve &
```

### 5. Initialize the database
```bash
python -m api.db.init_db
```

### 6. Start the API server
```bash
uvicorn api.main:app --reload
```

### 7. Start the frontend
```bash
cd frontend
python3 -m http.server 3000
```

---

## 🖥️ Using the Frontend

Once everything is running, open `http://localhost:3000` in your browser.

### Step 1 — Upload a PDF template
- Click **"Choose File"** and select any fillable PDF form
- Enter a name for the template
- Click **"Upload Template"**

FireForm will automatically extract all form field names and their human-readable labels.

### Step 2 — Fill the form
- Select your uploaded template from the dropdown
- In the text box, describe the incident or enter the information in natural language:

```
Employee name is John Smith. Employee ID is EMP-2024-789.
Job title is Firefighter Paramedic. Location is Station 12 Sacramento.
Department is Emergency Medical Services. Supervisor is Captain Rodriguez.
Phone number is 916-555-0147.
```

- Click **"Fill Form"**

FireForm sends one request to Ollama (Mistral) which extracts all fields at once and returns structured JSON.


### Batch fill — multiple agency forms at once

Switch to **BATCH** mode in the sidebar to fill multiple templates simultaneously from one transcript:

1. Click **BATCH** toggle in the sidebar
2. Check all agency templates you want to fill
3. Enter one incident description
4. Click **⚡ FILL N FORMS**

FireForm runs a single LLM call for the entire batch and returns individual download links for each filled PDF. One failed template never aborts the rest.

---
### Step 3 — Download the filled PDF
- Click **"Download PDF"** to save the completed form

---

## ✅ Supported PDF Field Types

FireForm supports all common fillable PDF field types:

| Field Type | Description | Example |
|------------|-------------|---------|
| Text | Plain text input | Name, ID, Notes |
| Checkbox | Boolean tick box | Married ✓ |
| Radio button | Single selection from options | Gender: Male / Female |
| Dropdown | Single select list | City |
| Multi-select | Multiple select list | Language |

**Checkbox and radio button filling:**
FireForm automatically detects the field type from the PDF annotation flags (`FT` and `Ff`) and writes the correct PDF value format. PDF checkboxes require named values like `/Yes` or `/Off` — not plain strings. FireForm reads the PDF's own appearance stream (`AP.N`) to find the exact on-state name used by each form, so it works correctly with any PDF regardless of internal naming conventions.

LLM outputs like `"yes"`, `"true"`, `"x"`, `"1"`, `"checked"` all resolve to the correct checked state. Outputs like `"no"`, `"false"`, `"0"`, `""` resolve to unchecked.

---

## 🤖 How AI Extraction Works

FireForm uses a **batch extraction** approach:

```
Traditional approach (slow):     FireForm approach (fast):
  Field 1 → Ollama call           All fields → 1 Ollama call
  Field 2 → Ollama call           Mistral returns JSON with all values
  Field 3 → Ollama call           Parse → fill PDF
  ...N calls total                1 call total (O(1))
```

Field names are automatically read from the PDF's annotations and converted to human-readable labels before being sent to Mistral — so the model understands what each field means regardless of internal PDF naming conventions like `textbox_0_0`.

**Example extraction:**
```json
{
  "NAME/SID":     "John Smith",
  "JobTitle":     "Firefighter Paramedic",
  "Department":   "Emergency Medical Services",
  "Phone Number": "916-555-0147",
  "email":        null
}
```

---

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

Expected output: **70 passed**

See [TESTING.md](TESTING.md) for full test coverage details.

---

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |

To use a remote Ollama instance:
```bash
export OLLAMA_HOST=http://your-server:11434  # Linux/Mac
set OLLAMA_HOST=http://your-server:11434     # Windows
```

---

## 🐳 Docker (Coming Soon)

Docker support is in progress. See [docker.md](docker.md) for current status.

---

## ❓ Troubleshooting

**`Form data requires python-multipart`**
```bash
pip install python-multipart
```

**`ModuleNotFoundError: No module named 'pypdf'`**
```bash
pip install pypdf
```

**`Could not connect to Ollama`**
- Make sure `ollama serve` is running
- Check Ollama is on port 11434: `curl http://localhost:11434`

**`NameError: name 'Union' is not defined`**
- Pull latest changes: `git pull origin main`
- This bug is fixed in the current version

**Tests fail with `ModuleNotFoundError: No module named 'api'`**
- Use `python -m pytest` instead of `pytest`

---

## 🗄️ Master Incident Data Lake

FireForm now ships with a persistent **Master Incident Data Lake** — a foundational backend architecture that decouples voice extraction from rigid single-PDF workflows, enabling the *"Record Once. Report Everywhere."* paradigm.

### What is the Data Lake?

Instead of extracting from a transcript → filling one PDF → discarding all data, FireForm now:

1. Extracts **all spoken intelligence** into a permanent, schema-less JSON record linked to a unique **Incident ID** (`INC-YYYY-MMDD-HHMM`).
2. Stores it in the database — independently of any PDF template.
3. Lets any officer, at any time, generate a filled PDF for **any registered agency template** from that same stored record — with zero new LLM calls.

```
Old approach:
  Transcript → LLM → PDF → ❌ Data discarded

Master Data Lake approach:
  Transcript → LLM → Master JSON (persisted) → PDF A
                                               → PDF B
                                               → PDF C  (any template, any time)
```

---

### Data Lake Workflow

#### Step 1 — Record an Incident

Enter your incident description in the text box and click **"Save to Data Lake"** (or use the API directly):

```
POST /incidents/extract?input_text=<transcript>&incident_id=<optional>
```

If no `incident_id` is provided, one is auto-generated. A unique Incident ID is returned:

```json
{
  "incident_id": "INC-2026-0401-0912",
  "status": "created",
  "fields_extracted": 7
}
```

> **Tip:** Copy and save your Incident ID. You will need it to append data or generate PDFs.

---

#### Step 2 — Append Data (Collaborative Reporting)

Multiple officers can contribute to the same incident record by passing the same `incident_id`:

```
POST /incidents/extract?input_text=<new transcript>&incident_id=INC-2026-0401-0912
```

FireForm's **Collaborative Consensus Merge** engine handles conflicts intelligently:

| Scenario | Behaviour |
|----------|-----------|
| New officer sends `null` for a field that already has data | Existing value is **protected** (not overwritten) |
| New officer adds a field not previously seen | Field is **added** to the Data Lake |
| Both officers mention `Notes` or `Description` | Values are **appended** with a timestamped `[UPDATE]` tag |
| New officer corrects a non-null field with a new value | Value is **updated** |

The response will include `"status": "merged"`.

---

#### Step 3 — Generate a PDF for Any Agency Template

Once the incident is stored, generate a filled PDF for any uploaded template:

```
POST /incidents/{incident_id}/generate/{template_id}
```

Example:
```
POST /incidents/INC-2026-0401-0912/generate/3
```

FireForm maps the stored Data Lake JSON to the selected template's fields and returns a download link:

```json
{
  "incident_id": "INC-2026-0401-0912",
  "template_name": "Fire Department Report",
  "submission_id": 12,
  "download_url": "/forms/download/12",
  "fields_matched": 6,
  "fields_total": 8
}
```

You can call this endpoint multiple times with different `template_id` values — one incident record, unlimited reports.

---

#### Step 4 — Inspect the Data Lake

Retrieve the full raw master JSON at any time:

```
GET /incidents/{incident_id}
```

List all stored incidents:

```
GET /incidents
```

---

### Data Lake API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/incidents/extract` | Extract transcript → store in Data Lake |
| `GET`  | `/incidents` | List all stored incidents |
| `GET`  | `/incidents/{id}` | Retrieve full master JSON for one incident |
| `POST` | `/incidents/{id}/generate/{template_id}` | Generate a PDF from stored data |

---

### Environment Variables (Updated)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_TIMEOUT` | `300` | LLM request timeout in seconds (increase for slow hardware) |

To customise:
```bash
export OLLAMA_HOST=http://your-server:11434    # Linux/Mac
export OLLAMA_TIMEOUT=300                       # Linux/Mac

set OLLAMA_HOST=http://your-server:11434       # Windows
set OLLAMA_TIMEOUT=300                          # Windows
```

---

### Running Data Lake Tests

The Data Lake test suite uses an in-memory SQLite database and mocks the LLM — **no Ollama instance required**:

```bash
python -m pytest tests/test_incidents.py -v
```

Expected output: **13 passed**

Full test suite:
```bash
python -m pytest tests/ -v
```

---

## 🧠 Dynamic AI Semantic Mapper

Building on top of the Master Data Lake, the **AI Semantic Mapper** is the intelligent bridge between unstructured extracted JSON and any rigid PDF form schema — making FireForm truly universal.

### The Problem It Solves

The Data Lake captures all spoken intelligence with dynamically invented keys:
```json
{ "Speaker": "Jack Portman", "Identity": "EMP-001", "Reporting Location": "742 Evergreen" }
```

But a Fire Department PDF may demand completely different key names:
```json
{ "FullName": "", "BadgeNumber": "", "IncidentAddress": "" }
```

Standard Python dictionary matching would silently drop all three values (zero matches). The Semantic Mapper eliminates this failure mode entirely.

---

### How It Works

```
Data Lake JSON                 Mistral LLM               PDF Form
──────────────                 ───────────               ────────
"Speaker": "Jack"   ──────→   [Semantic       ──────→   "FullName": "Jack"
"Identity": "EMP1"  ──────→    Understanding] ──────→   "BadgeNumber": "EMP1"
"Location": "742"   ──────→                   ──────→   "IncidentAddress": "742"
"VictimInjury": X   ──────→   (not needed     ──────→   (null — not in PDF)
                               for this PDF)
```

At PDF generation time, FireForm sends Mistral two things:
1. The full Data Lake JSON for the incident
2. The target PDF's field name list

Mistral understands human semantics — it knows `"Speaker"` means `"FullName"`, `"Identity"` means `"BadgeNumber"` — and returns a perfectly keyed JSON object matched exactly to the PDF's requirements. No hardcoded `if/else` chains. No per-template Python logic. Ever.

---

### Resilience & Fallback

The Semantic Mapper is wrapped in a two-layer fallback:

| Scenario | Behaviour |
|----------|-----------|
| Mapper succeeds | PDF fields filled via AI semantic understanding |
| Mapper returns empty `{}` | Falls back to exact-string key matching from Data Lake |
| Mapper raises exception (timeout/crash) | Falls back to exact-string key matching from Data Lake |

The PDF is **always generated** — the fallback ensures zero 500 errors from LLM timeouts.

---

### Pure Schema-less Mode

When no templates exist in the database, the extraction engine switches to a fully ad-hoc mode:

```
No template uploaded?
  → Mistral invents ALL keys dynamically from transcript alone
  → "VictimInjury", "WeaponType", "SuspectDescription" — all captured
  → Stored in Data Lake for future PDF generation against any template
```

This enables FireForm to capture intelligence even before the relevant PDF template is registered.

---

### Running AI Semantic Mapper Tests

The Semantic Mapper test suite mocks all Ollama calls — **no running Ollama instance required**:

```bash
python -m pytest tests/test_semantic_mapper.py -v
```

Key test cases:
- ✅ Correctly maps exact-match keys
- ✅ Resolves synonym mismatches (`"Speaker"` → `"FullName"`)
- ✅ Returns `{}` gracefully on LLM failure (no crash)
- ✅ Handles empty Data Lake JSON
- ✅ Handles invalid/non-JSON LLM response
- ✅ Generate endpoint uses Mapper output to fill PDF
- ✅ Fallback triggers correctly when mapper returns `{}`
- ✅ Fallback triggers correctly when mapper raises exception
- ✅ 404 handling unaffected by Mapper

Expected output: **9 passed**

---

### Environment Variables (AI Semantic Mapper)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_TIMEOUT` | `300` | Seconds to wait for LLM response. Increase for slow local hardware. |

> **Note:** The Semantic Mapper makes one additional Ollama call per PDF generation. On a typical local machine, this takes 10–60 seconds depending on hardware. If your machine is slow, set `OLLAMA_TIMEOUT=600`.