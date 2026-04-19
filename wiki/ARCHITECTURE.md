# FireForm Architecture

FireForm is a system designed to automate the process of filling out PDF forms using information extracted from transcriptions via an LLM.

## Pipeline Description

The FireForm pipeline follows a structured flow from receiving raw user input to generating a finalized, filled PDF document.

### High-Level Flow

1.  **Template Preparation**: A standard PDF is processed to ensure it has interactive form fields.
2.  **Input Acquisition**: The system receives a transcript (text) and a list of target fields to extract.
3.  **LLM Extraction**: An LLM (via Ollama) processes the transcript to find values for each target field.
4.  **Form Filling**: Extracted values are mapped and written into the PDF template.
5.  **Output Generation**: A new, filled PDF is saved with a timestamped filename.

### Component Interaction

```mermaid
sequenceDiagram
    participant U as User/Frontend
    participant FM as FileManipulator
    participant LLM as LLM Module
    participant O as Ollama (Mistral)
    participant F as Filler
    participant CF as CommonForms/pypdf

    U->>FM: fill_form(transcript, fields, pdf_path)
    FM->>LLM: Set target_fields & transcript
    FM->>F: fill_form(pdf_path, llm)
    
    activate F
    F->>LLM: main_loop()
    
    activate LLM
    loop For each field
        LLM->>LLM: build_prompt(field)
        LLM->>O: POST /api/generate
        O-->>LLM: Extracted Value
        LLM->>LLM: add_response_to_json(field, value)
    end
    LLM-->>F: Resulting JSON Data
    deactivate LLM

    F->>CF: Read PDF Template
    F->>F: Sort Annotations (Visual Order)
    F->>CF: Write values to Widgets
    F->>CF: Write Filled PDF
    F-->>FM: Path to filled PDF
    deactivate F

    FM-->>U: Final PDF Path
```

### Key Components

-   **`FileManipulator`**: The high-level orchestrator that manages the overall process.
-   **`LLM`**: Handles prompt engineering and communication with the local Ollama instance. It extracts structured data from unstructured text.
-   **`Filler`**: Handles the low-level PDF manipulation, ensuring that extracted data is placed into the correct form fields.
-   **`commonforms`**: A dependency used to prepare standard PDFs for filling.
-   **`pdfrw` / `pypdf`**: Libraries used for reading and writing PDF metadata and form field values.
