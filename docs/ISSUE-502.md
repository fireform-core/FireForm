# Issue #502 — Allow users to choose AI models

## Summary

The API now lets clients discover available Ollama models, choose a model for
form filling, and download models through the backend.

## Implemented changes

- `GET /api/v1/forms/models`
  - Returns the configured `current_model`.
  - Returns recommended models even when they are not installed.
  - Marks each model with `installed` and `recommended`.
  - Includes additional models reported by Ollama.
  - Still returns a valid response when Ollama is unavailable.
- `POST /api/v1/forms/fill`
  - Accepts an optional `model` field.
  - Uses the configured `OLLAMA_MODEL` when no override is supplied.
  - Transmits an explicit model through the service layer to Ollama.
  - Returns `422 MODEL_NOT_INSTALLED` when Ollama reports HTTP 404 for a model.
- `POST /api/v1/forms/pull`
  - Streams Ollama progress as newline-delimited JSON.
  - Uses `OLLAMA_PULL_TIMEOUT`, separate from inference timeout.
  - Ends with `{"status":"success"}` on a completed pull.
  - Reports stream failures as an `error` object because the HTTP status is
    already committed.
- `contracts/`
  - Documents the new routes, request schemas, response schemas, and NDJSON
    response format.

## Configuration

```env
OLLAMA_TIMEOUT=300
OLLAMA_PULL_TIMEOUT=600
```

`OLLAMA_TIMEOUT` applies to inference. `OLLAMA_PULL_TIMEOUT` applies only to
model downloads.

## Automated tests

Run the focused tests inside the application container:

```powershell
docker exec fireform-app python3 -m pytest tests/test_form_filler.py tests/test_api.py -q --tb=short
```

Expected result:

```text
31 passed
```

The pull endpoint tests can be run separately:

```powershell
docker exec fireform-app python3 -m pytest tests/test_api.py -q -k "pull_model" --tb=short
```

Expected result:

```text
2 passed
```

## Manual verification

### List models

```powershell
Invoke-RestMethod `
  http://localhost:8000/api/v1/forms/models |
  ConvertTo-Json -Depth 5
```

### Pull a model

```powershell
$body = @{ model = "qwen2.5:3b" } | ConvertTo-Json

Invoke-WebRequest `
  -Uri http://localhost:8000/api/v1/forms/pull `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Confirm afterwards that the selected model has `"installed": true` in
`GET /api/v1/forms/models`.

### Fill with an explicit model

```powershell
$body = @{
    template_id = 4
    input_text = "A wildfire occurred near the main station. Three firefighters and one engine responded."
    model = "qwen2.5:1.5b"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://localhost:8000/api/v1/forms/fill `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

### Verify the default-model fallback

Repeat the fill request without the `model` property. The backend should use
the model configured by `OLLAMA_MODEL`.

### Verify the missing-model error

Use a model name that is not installed. The response should be HTTP `422` with
`error_code` equal to `MODEL_NOT_INSTALLED` and a message explaining that the
model must first be pulled.

## Performance note

Large ICS narratives and schemas can take several minutes with larger models
when Ollama runs on CPU. A read timeout does not indicate that the model is
missing; check `/api/v1/health` and `/api/v1/forms/models` first. For a quick
functional check, use a short narrative and `qwen2.5:1.5b`.

## Local test artifacts

Generated PDFs under `data/inputs/` are local test artifacts and should not be
staged or committed.
