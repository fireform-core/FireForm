# 🔥 FireForm

FireForm is the 1st Place Winner of the Reboot the Earth hackathon, hosted by the United Nations (UN) and UC Santa Cruz (UCSC).

It is an open-source, agnostic system built to solve administrative overhead for first responders. FireForm is a Digital Public Good (DPG) designed to help departments like Cal Fire save hundreds of hours by eliminating redundant paperwork.

## 🚩 The Problem

First responders, like firefighters, are often required to report a single incident to multiple different agencies (e.g., county sheriff, local PD, emergency medical services). Each agency has its own unique forms and templates. This forces firefighters to spend hours at the end of their shift filling out the same information over and over, taking them away from critical duties.

## 💡 The Solution

FireForm is a centralized "report once, file everywhere" system.
- **Single Input:** A firefighter records a single voice memo or fills out one "master" text field describing the entire incident.
- **AI Extraction:** The transcription is sent to an open-source LLM (via Ollama) which extracts all the key information (names, locations, incident details) into a structured JSON file.
- **Template Filling:** FireForm then takes this single JSON object and uses it to automatically fill every required PDF template for all the different agencies.

The result is hours of time saved per shift, per firefighter.

### ✨ Key Features
- **Agnostic:** Works with any department's existing fillable PDF forms.
- **AI-Powered:** Uses open-source, locally-run LLMs (Mistral) to extract data from natural language. No data ever needs to leave the local machine.
- **Single Point of Entry:** Eliminates redundant data entry entirely.
- **Verification Layer:** Verifies every resulting PDF output field to guarantee AI extracted answers were successfully assigned, ensuring 100% data fidelity.

Example Verification Log:
```bash
[LOG]: Starting PDF fill verification...
[!] Mismatch at field index 0: Expected 'John', Found ''
[LOG]: Verification Summary: ✔ Correct 5 | ✖ Mismatch 1 | ⚠ Missing 0
```
Open-Source (DPG): Built 100% with open-source tools to be a true Digital Public Good, freely available for any department to adopt and modify.

## 🤝 Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for all. Please see our [Code of Conduct](CODE_OF_CONDUCT.md) for more information.

## 🚀 Contributing

Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) to learn how you can help.

## ⚖️ License



This project is licensed under the MIT License. See the LICENSE file for details.

## 🏆 Acknowledgements and Contributors
This project was built in 48 hours for the Reboot the Earth 2025 hackathon. Thank you to the United Nations and UC Santa Cruz for hosting this incredible event and inspiring us to build solutions for a better future.

## 📜 Citation

If you use FireForm in your research or project, please cite it using the following metadata:

[![Cite this repository](https://img.shields.io/badge/Cite-FireForm-blue.svg)](CITATION.cff)

You can also use the "Cite this repository" button in the GitHub repository sidebar to export the citation in your preferred format.

__Contributors:__ 
- Juan Álvarez Sánchez (@juanalvv)
- Manuel Carriedo Garrido
- Vincent Harkins (@vharkins1)
- Marc Vergés (@marcvergees) 
- Jan Sans
