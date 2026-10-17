# Model Selection

FireForm uses Ollama for local form filling. This page documents the API for
discovering, selecting, and downloading models.

## Model discovery

### `GET /api/v1/forms/models`

Returns the configured default model and the available models:

| Field | Meaning |
|---|---|
| `current_model` | Model used when no override is supplied |
| `name` | Ollama model name |
| `installed` | Whether the model is installed locally |
| `recommended` | Whether FireForm recommends the model |

Recommended models are included even when they are not installed. Additional
installed Ollama models are included as well. If Ollama is unavailable or
returns malformed data, recommended models are returned with
`installed: false`.

## Selecting a model

`POST /api/v1/forms/fill` accepts an optional `model` override:

```json
{
  "template_id": 4,
  "input_text": "A wildfire occurred near the main station.",
  "model": "qwen2.5:1.5b"
}
```

When `model` is omitted, the configured `OLLAMA_MODEL` is used. Model names
must be 128 characters or fewer and match:

```text
^[A-Za-z0-9][A-Za-z0-9._\-/:]*$
```

If the selected model is not installed, the API returns HTTP `422` with the
error code `MODEL_NOT_INSTALLED`.

## Downloading a model

### `POST /api/v1/forms/pull`

Downloads a model and streams progress as newline-delimited JSON (NDJSON):

```json
{ "model": "qwen2.5:3b" }
```

Example successful stream:

```text
{"status":"pulling manifest"}
{"status":"downloading","completed":1048576,"total":1929912432}
{"status":"success"}
```

The final event is `{"status":"success"}` only after a successful download.
If a download fails after streaming starts, clients must inspect the stream
for an `error` event:

```text
{"status":"pulling manifest"}
{"error":"Ollama connection refused"}
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | See `.env.example` | Default model |
| `OLLAMA_TIMEOUT` | `300` | Seconds allowed for inference |
| `OLLAMA_PULL_TIMEOUT` | `120` | Seconds to wait without receiving progress from Ollama before giving up on a model download; not a limit on total download time. Connecting to Ollama is limited to 10 seconds. |

Docker values are documented in `docker/.env.example`.
