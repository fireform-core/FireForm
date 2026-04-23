# FireForm Architecture Overview

This document provides a high-level overview of the FireForm pipeline to help contributors understand how natural language incident descriptions are transformed into structured data and populated into PDF forms.

## Pipeline
`User input → textToJSON → Ollama extraction → JSON → Fill → PDF output`

FireForm converts natural language descriptions into structured data and automatically fills PDF templates using this extracted information.

## Components

### main.py
Acts as the orchestration layer, coordinating extraction and PDF filling by invoking backend components.

### textToJSON (backend.py)
Responsible for field-wise information extraction using a locally hosted Ollama model. For each target form field, a prompt is generated and sent to the model to identify relevant values in the transcript.

### Fill (backend.py)
Handles PDF automation by reading form templates, ordering fields visually (top-to-bottom, left-to-right), and inserting extracted values before saving the filled document.

### inputs/
Contains sample input data and templates used for testing and experimentation.

### outputs/
Stores generated artifacts such as structured JSON data and filled PDF forms.

## Notes
- Extraction is performed locally via Ollama to preserve privacy
- Each target field is extracted independently using prompt-based querying
- PDF fields are filled based on visual ordering rather than semantic field matching
- The modular structure enables future improvements such as schema validation, mapping strategies, and extraction optimization