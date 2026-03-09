# 🧪 Testing

This document describes how to run the FireForm test suite locally.

## Prerequisites

Make sure you have installed all dependencies:

```bash
pip install -r requirements.txt
```

## Running Tests

From the project root directory:

```bash
python -m pytest tests/ -v
```

> **Note:** Use `python -m pytest` instead of `pytest` directly to ensure the project root is on the Python path.

## Test Coverage

| File | Tests | What it covers |
|------|-------|----------------|
| `tests/test_llm.py` | 15 | LLM class — batch prompt, field extraction, plural handling |
| `tests/test_templates.py` | 10 | `POST /templates/create`, `GET /templates`, `GET /templates/{id}` |
| `tests/test_forms.py` | 7 | `POST /forms/fill`, `GET /forms/{id}`, `GET /forms/download/{id}` |

**Total: 52 tests**

## Test Design

- All tests use an **in-memory SQLite database** — your local `fireform.db` is never touched
- Each test gets a **fresh empty database** — no data leaks between tests
- Ollama is **never called** during tests — all LLM calls are mocked

## Key Test Cases

**LLM extraction (`test_llm.py`)**
- Batch prompt contains all field keys and human-readable labels
- `main_loop()` makes exactly **1 Ollama call** regardless of field count (O(1) assertion)
- Graceful fallback when Mistral returns invalid JSON
- `-1` responses stored as `None`, not as the string `"-1"`

**Template endpoints (`test_templates.py`)**
- Valid PDF upload returns 200 with field data
- Non-PDF upload returns 400
- Missing file returns 422
- Non-existent template returns 404

**Form endpoints (`test_forms.py`)**
- Non-existent template returns 404
- Ollama connection failure returns 503
- Missing filled PDF on disk returns 404
- Non-existent submission returns 404
