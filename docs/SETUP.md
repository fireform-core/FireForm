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


---

## 📱 PWA Mobile Companion (Field Capture)

FireForm includes an offline-first Progressive Web App at `/mobile` that lets first responders capture incident data in the field — no internet required.

> **Current Status:** The PWA is a working proof of concept. The long-term goal is a fully native mobile app. The PWA approach is the current implementation while the native app is in development.

---

### How It Works

```
At the scene (no WiFi):
  Officer opens PWA on phone
  Records voice, types notes, captures GPS
  Saves draft — stored on device

Back at station (WiFi restored):
  PWA detects connection automatically
  Draft syncs to station server
  Audio transcribed, PDF filled
  Officer downloads completed forms
```

---

### Setup — Running PWA on Your Network

**Step 1 — Start the API server exposed to your network:**
```cmd
uvicorn api.main:app --host 0.0.0.0 --reload
```

**Step 2 — Find your PC's local IP:**
```cmd
ipconfig
```
Look for `IPv4 Address` under your WiFi adapter — e.g. `192.168.1.105`

**Step 3 — Open on mobile (same WiFi):**
```
http://192.168.1.105:8000/mobile
```

This works for basic text capture and drafts. However, **microphone and GPS require HTTPS** — this is a browser security requirement, not a FireForm limitation.

---

### Enabling Microphone and GPS — ngrok (Recommended for Demo)

[ngrok](https://ngrok.com) creates a secure HTTPS tunnel to your local server. This is the recommended approach for demo and testing purposes.

**Install ngrok:**
1. Download from https://ngrok.com/download
2. Create a free account at https://dashboard.ngrok.com/signup
3. Copy your authtoken from the dashboard
4. Run: `ngrok config add-authtoken YOUR_TOKEN`

**Start the tunnel:**
```cmd
# Terminal 1 — API server
uvicorn api.main:app --host 0.0.0.0 --reload

# Terminal 2 — ngrok tunnel
ngrok http 8000
```

ngrok will show a URL like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

**Open on mobile:**
```
https://abc123.ngrok-free.app/mobile
```

Now microphone ✅, GPS ✅, and PWA install ✅ all work.

> **Note:** Free ngrok sessions expire after a few hours and the URL changes on restart. For persistent access during a demo session, keep both terminals running.

---

### Installing as an App on Android

1. Open the ngrok HTTPS URL in Chrome on your Android device
2. Tap the three-dot menu → **Add to Home Screen**
3. Tap **Install**

The app now appears as an icon on your home screen and opens in standalone mode (no browser bar).

---

### Installing as an App on iOS

1. Open the ngrok HTTPS URL in Safari on your iPhone/iPad
2. Tap the Share button → **Add to Home Screen**
3. Tap **Add**

---

### Offline Behaviour After Install

Once installed via HTTPS, the Service Worker caches the app shell. After the first visit:
- The app opens even with zero internet
- Drafts save to IndexedDB on the device
- GPS works (satellite-based, no internet needed)
- Voice records and stores locally
- Everything syncs automatically when WiFi is restored

---

### Production Deployment — Station Network

For real station deployment, replace ngrok with a self-signed SSL certificate on the station PC:

```bash
# Generate self-signed certificate (Linux/Mac)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Start uvicorn with SSL
uvicorn api.main:app --host 0.0.0.0 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Officers connect via station WiFi:
```
https://STATION_PC_IP:8000/mobile
```

All data stays on-premise. No external services. No cloud.

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