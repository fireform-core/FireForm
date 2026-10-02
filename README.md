# 🔥 FireForm

[![Digital Public Goods](https://img.shields.io/badge/Digital_Public_Good-United_Nations-blue.svg)](https://fireform-core.github.io/FireForm/dpg.html)

**FireForm is a recognized Digital Public Good (DPG) from the United Nations** and the 1st Place Winner of the Reboot the Earth hackathon, hosted by the UN and UC Santa Cruz (UCSC).

It is an open-source, agnostic system built to solve administrative overhead for first responders, designed to help departments like Cal Fire save hundreds of hours by eliminating redundant paperwork.

## 🚩 The Problem

First responders, like firefighters, are often required to report a single incident to multiple different agencies (e.g., county sheriff, local PD, emergency medical services). Each agency has its own unique forms and templates. This forces firefighters to spend hours at the end of their shift filling out the same information over and over, taking them away from critical duties.

## 💡 The Solution

FireForm is a centralized "report once, file everywhere" system.
- **Single Input:** A firefighter records a single voice memo or fills out one "master" text field describing the entire incident.
- **AI Extraction:** The transcription is sent to an open-source LLM (via Ollama) which extracts all the key information (names, locations, incident details) into a structured JSON file.
- **Template Filling:** FireForm then takes this single JSON object and uses it to automatically fill every required PDF template for all the different agencies.

The result is hours of time saved per shift, per firefighter.

### ✨ Key Features
- **Desktop App:** Download the native desktop app for macOS, Windows, or Linux from [Releases](https://github.com/fireform-core/FireForm/releases).
- **Agnostic:** Works with any department's existing fillable PDF forms.
- **AI-Powered:** Uses open-source, locally-run LLMs (Mistral) to extract data from natural language. No data ever needs to leave the local machine.
- **Single Point of Entry:** Eliminates redundant data entry entirely.

Open-Source (DPG): Built 100% with open-source tools to be a true Digital Public Good, freely available for any department to adopt and modify.

## 🤝 Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for all. Please see our [Code of Conduct](CODE_OF_CONDUCT.md) for more information.

## 🚀 Contributing

Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) to learn how you can help.

## ⚖️ License



This project is licensed under the MIT License. See the LICENSE file for details.

## 🖥️ Desktop App

FireForm is available as a native desktop application for **macOS**, **Windows**, and **Linux**.

### Download

Grab the latest installer from the [Releases](https://github.com/fireform-core/FireForm/releases) page:
- **macOS:** `.dmg`
- **Windows:** `.exe` (NSIS installer)
- **Linux:** `.AppImage`

### Run from Source

```bash
cd frontend
npm install
npm start
```

> **Note:** The desktop app is a thin Electron wrapper around the same web frontend. The backend (API + Ollama) still needs to be running — see the [Deployment Guide](https://github.com/fireform-core/FireForm/wiki/DEPLOYMENT).

## 🏆 Acknowledgements and Contributors
This project was built in 48 hours for the Reboot the Earth 2025 hackathon. Thank you to the United Nations and UC Santa Cruz for hosting this incredible event and inspiring us to build solutions for a better future.

## 📜 Citation

If you use FireForm in your research or project, please cite it using the following metadata:

[![Cite this repository](https://img.shields.io/badge/Cite-FireForm-blue.svg)](CITATION.cff)

You can also use the "Cite this repository" button in the GitHub repository sidebar to export the citation in your preferred format.

## 📝 Ownership & Accountability

FireForm is an **Open Software** Digital Public Good. Ownership and accountability for the software code and its assets are clearly defined and lie with the core creators. This ownership is officially documented in our public [LICENSE](LICENSE) file, on our [public website](https://fireform-core.github.io/FireForm/dpg.html), and listed below.

__Contributors (Accountable Entity):__ 
- Juan Álvarez Sánchez (@juanalvv)
- Manuel Carriedo Garrido
- Vincent Harkins (@vharkins1)
- Marc Vergés (@marcvergees) 
- Jan Sans

## 🔓 Platform Independence

FireForm is built entirely on open-source technologies and has **no mandatory proprietary dependencies**, ensuring complete platform independence.
- **Frontend:** Built with React and packaged with Electron (Node.js). Dependencies are listed in `frontend/package.json`.
- **Backend:** Built with Python (FastAPI, SQLite). Dependencies are listed in `requirements.txt`.
- **AI System (Optional):** Uses [Ollama](https://ollama.com/) running open-weight LLMs (e.g., Mistral), ensuring all AI processing is done locally and openly. *Note: The AI features are optional and not core to the main functionality of FireForm (which operates as a digital form and template manager). The AI extraction can be disabled in the application settings. Furthermore, this local Ollama dependency can be swapped with any other LLM service.*

All dependencies can be verified through the [GitHub dependency graph (SBOM)](https://github.com/fireform-core/FireForm/network/dependencies). There are no vendor lock-ins, and any external service is designed to be replaceable with open alternatives without overhauling the core product.

## 💾 Mechanism for Extracting Data

FireForm is designed from the ground up to ensure that all generated and collected data is fully accessible and not locked into proprietary formats.
- **Data Format:** Any information (both non-PII and PII) extracted by the local LLM is generated and exported natively as a standard, non-proprietary **JSON** file.
- **Data Storage:** User preferences and template mappings are stored locally using **SQLite**, an open-source database engine.
- **Export Mechanism:** All structured data can be easily imported, exported, or exposed via the local FastAPI endpoints. No closed formats or proprietary databases are used.

## 🧭 Template Descriptions

Every template carries a **description**: a short statement of what that form is for. It is sent to the local LLM alongside the narrative each time the template is filled, so the model has context on the form's purpose before it reads a single value.

This is what lets one narrative fill very different forms correctly. A narrative saying *"dispatched Unit 12 to the Blackwood Canyon fire"* is unambiguous against an incident communications plan, but ambiguous against a fire incident report or a station duty roster. The description tells the model which document it is looking at.

`description` is **required** when creating a template:

```bash
curl -X POST http://localhost:8000/api/v1/templates/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ICS 205A Incident Radio Communications Plan",
    "description": "Radio communications plan for a Type 1 ICS incident. Assigns each operational branch a talkgroup and a primary contact.",
    "pdf_path": "src/templates/ics_205a.pdf",
    "fields": {}
  }'
```

### Writing a good description

- **Describe the form, not the incident.** The incident comes from the narrative at fill time. "Radio communications plan for a Type 1 incident" is useful; "wildfire near Blackwood Canyon" is not - it would bias every form filled from the template.
- **Say what kind of form it is and what it covers.** Purpose, scope, and the agency or standard it comes from are all useful signal.
- **Keep it to a sentence or two.** This is context, not an instruction sheet. Field-level meaning is already carried by each PDF field's own description.
- **Leave out personal data.** Template descriptions are stored in the database and replayed on every fill.

An empty string is accepted for templates that need no extra context, in which case the block is omitted from the prompt entirely.

## 🔒 Privacy & Applicable Laws

FireForm is built on a **local-first architecture**: all processing (including AI extraction) occurs locally on the operator's hardware and nothing is transmitted to external servers by default. However, operators should be aware of the following:

- **PII is processed locally.** Incident descriptions, names, dates, and other personally identifiable information are extracted by the local LLM, written into filled PDF files, and persisted in the local database (`FormSubmission` records). These files and records remain on disk until explicitly deleted.
- **No external transmission.** Data does not leave the machine by default. Audio transcription (Whisper) and LLM inference (Ollama) are both local services.
- **Operator responsibility.** Because PII is stored locally, the security of that data depends entirely on the operator's host system, filesystem permissions, backup practices, and access controls.

For complete details on data handling and compliance guidance, please review our public [Privacy Policy](https://fireform-core.github.io/FireForm/privacy.html).

## 🗑️ Data Deletion & Retention

FireForm provides API endpoints and an automated purge mechanism to manage stored PII.

### Deleting individual records

```bash
# Delete a single form submission (removes DB record + output PDF)
curl -X DELETE http://localhost:8000/api/v1/forms/{submission_id} \
  -H "X-API-Key: your-key"

# Delete a template and all associated submissions
curl -X DELETE http://localhost:8000/api/v1/templates/{template_id} \
  -H "X-API-Key: your-key"
```

### Bulk purge

```bash
# Purge all submissions older than 30 days
curl -X POST "http://localhost:8000/api/v1/forms/purge?days=30" \
  -H "X-API-Key: your-key"
```

### Automated retention

Set `RETENTION_PERIOD_DAYS` in `docker/.env.dev` (default: `30`). Celery Beat will automatically run a purge job every night at 03:00 UTC:

```env
RETENTION_PERIOD_DAYS=30
```

To enable the scheduler: `celery -A app.core.celery beat -l info`

## 🔑 Access Control

Deletion and purge endpoints can be protected by setting an API key:

```env
FIREFORM_API_KEY=your-strong-secret-key
```

When set, all `DELETE` and `POST /purge` requests must include one of:
- **Header:** `X-API-Key: your-strong-secret-key`
- **Bearer token:** `Authorization: Bearer your-strong-secret-key`

Read-only endpoints (list, preview, fill) do **not** require authentication.

## 🛡️ Operator Hardening Recommendations

- **Filesystem permissions:** Restrict access to `data/inputs/` and `data/outputs/` to the application user only (`chmod 700`).
- **Backups:** Encrypt any backups containing output PDFs.
- **HTTPS:** Deploy behind a reverse proxy (e.g., nginx) with TLS enabled.
- **API key rotation:** Rotate `FIREFORM_API_KEY` regularly and never commit it to version control.
- **Retention policy:** Configure `RETENTION_PERIOD_DAYS` in line with applicable regulations (HIPAA, GDPR, CCPA).

## 🛡️ Do No Harm by Design

FireForm is built to anticipate and prevent harm:
- **Data Privacy & Security (9A):** We handle sensitive incident data entirely offline. By never transmitting data to the cloud, we natively prevent online data breaches of PII. Operators are responsible for securing local storage; see the Operator Hardening Recommendations above.
- **Inappropriate Content (9B):** The application is an internal productivity tool without public social interactions or user-generated content hosting, completely mitigating the risks of public harassment or illegal content distribution.
- **Protection from Harassment (9C):** For our open-source contributor community, we strictly enforce our [Code of Conduct](CODE_OF_CONDUCT.md) to ensure a safe, harassment-free environment for all contributors.

## 🏅 Standards & Best Practices

FireForm strictly aligns with globally recognized standards and best practices to ensure interoperability and sustainable implementation:

**Featured Standards:**
- **JSON & UTF-8:** All data extraction and templates rely on standard JSON and UTF-8 encoding.
- **OpenAPI & REST:** The Python FastAPI backend automatically adheres to the OpenAPI specification and RESTful architectural standards.

**Featured Best Practices:**
- **Community:** We enforce a strict [Code of Conduct](CODE_OF_CONDUCT.md) and provide clear [Contribution Guidelines](CONTRIBUTING.md).
- **Lifecycle Management:** We use Git for Change Management, strictly adhere to Semantic Versioning (SemVer), and utilize Tagged Releases.
- **Interoperability & Architecture:** We employ Open Standards (JSON/SQLite), Programmatic APIs (FastAPI), and strict Dependency Management (`package.json`, `requirements.txt`).
