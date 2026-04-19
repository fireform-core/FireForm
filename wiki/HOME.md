# Welcome to the FireForm Wiki!

FireForm is the 1st Place Winner of the Reboot the Earth hackathon, hosted by the United Nations (UN) and UC Santa Cruz (UCSC).

It is an open-source, agnostic system built to solve administrative overhead for first responders. FireForm is a Digital Public Good (DPG) designed to help departments like Cal Fire save hundreds of hours by eliminating redundant paperwork.

## 🚀 Navigation

- [[ARCHITECTURE]]: High-level system design and component interaction.
- [[DEPLOYMENT]]: Step-by-step guide to getting FireForm running.
- [[DATABASE]]: Information on database setup and management.
- [[DOCKER]]: Detailed guide on using Docker and Docker Compose.
- [[CONTRIBUTING]]: How you can help improve FireForm.

## 🚩 The Problem

First responders, like firefighters, are often required to report a single incident to multiple different agencies. Each agency has its own unique forms and templates. This forces firefighters to spend hours at the end of their shift filling out the same information over and over.

## 💡 The Solution

FireForm is a centralized **"report once, file everywhere"** system.

1.  **Single Input:** A firefighter records a single voice memo or fills out one "master" text field.
2.  **AI Extraction:** The transcription is sent to an open-source LLM (via Ollama) which extracts all key information into structured JSON.
3.  **Template Filling:** FireForm uses this JSON to automatically fill every required PDF template.

### ✨ Key Features

- **Agnostic:** Works with any department's existing fillable PDF forms.
- **AI-Powered:** Uses open-source, locally-run LLMs (Mistral). No data leaves the local machine.
- **Single Point of Entry:** Eliminates redundant data entry entirely.
- **Open-Source (DPG):** Built 100% with open-source tools.
