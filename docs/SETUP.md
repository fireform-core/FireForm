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

### Step 3 — Download the filled PDF
- Click **"Download PDF"** to save the completed form

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

Expected output: **52 passed**

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