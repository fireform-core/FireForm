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
- **AI System:** Uses [Ollama](https://ollama.com/) running open-weight LLMs (e.g., Mistral), ensuring all AI processing is done locally and openly.

All dependencies can be verified through the [GitHub dependency graph (SBOM)](https://github.com/fireform-core/FireForm/network/dependencies). There are no vendor lock-ins, and any external service is designed to be replaceable with open alternatives without overhauling the core product.

## 💾 Mechanism for Extracting Data

FireForm is designed from the ground up to ensure that all generated and collected data is fully accessible and not locked into proprietary formats.
- **Data Format:** Any information (both non-PII and PII) extracted by the local LLM is generated and exported natively as a standard, non-proprietary **JSON** file.
- **Data Storage:** User preferences and template mappings are stored locally using **SQLite**, an open-source database engine.
- **Export Mechanism:** All structured data can be easily imported, exported, or exposed via the local FastAPI endpoints. No closed formats or proprietary databases are used.

## 🔒 Privacy & Applicable Laws

FireForm is built on a local-first architecture, ensuring that all processing (including AI extraction) occurs locally on the user's hardware. We do not collect, process, or share any Personally Identifiable Information (PII) with third parties. By keeping data completely offline, FireForm natively assists deploying organizations in complying with strict data protection laws such as **HIPAA**, **CCPA**, and **GDPR**. 

For complete details on our data handling and consent management procedures, please review our public [Privacy Policy](https://fireform-core.github.io/FireForm/privacy.html).

## 🛡️ Do No Harm by Design

FireForm is built to anticipate and prevent harm:
- **Data Privacy & Security (9A):** We handle sensitive incident data entirely offline. By never transmitting data to the cloud, we natively prevent online data breaches of PII.
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
