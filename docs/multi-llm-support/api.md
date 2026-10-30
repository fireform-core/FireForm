# API

Contract: `contracts/path/system.yaml` and `contracts/path/forms.yaml`.

Provider credentials, custom endpoints, external-processing consent, and
manually entered model IDs can also be managed through the endpoints described
in [User configuration](user-configuration.md).

## List providers and models

`GET /api/v1/system/llm/models`

Add `?refresh=true` to skip the cache. Lists are cached for 60 seconds, failures for 10.

```json
{
  "default": { "provider": "gemini", "model": "gemini-2.5-flash" },
  "providers": [
    {
      "provider": "ollama",
      "available": true,
      "default_model": "qwen2.5:1.5b",
      "models": [
        {
          "name": "qwen2.5:1.5b",
          "size_gb": 0.92,
          "quantization": "Q4_K_M",
          "loaded": false,
          "installed": true
        }
      ],
      "downloadable": [
        { "name": "qwen2.5:3b", "installed": false },
        { "name": "llama3.2:3b", "installed": false }
      ]
    },
    {
      "provider": "gemini",
      "available": true,
      "default_model": "gemini-2.5-flash",
      "models": [{ "name": "gemini-2.5-flash" }, { "name": "gemini-2.5-pro" }]
    },
    {
      "provider": "anthropic",
      "available": false,
      "detail": "anthropic rejected the API key: Invalid Anthropic API Key. Check ANTHROPIC_API_KEY.",
      "error_code": "LLM_AUTH_FAILED",
      "models": []
    }
  ]
}
```

- Only enabled providers appear.
- Hosted models carry `name` only. Ollama adds `size_gb`, `quantization`, `loaded`, and `installed`.
- `downloadable` lists Ollama models that may be pulled but are not on the host yet (`installed: false`). It appears only for Ollama and is omitted when no models are downloadable (for example, when all installable models are already installed). Hosted providers omit `downloadable` and `installed`.
- With an explicit `_MODELS` list, names the provider does not offer are left out of `models` and appear in `downloadable` (Ollama only).
- Empty fields are left out of the response.

## Pull an Ollama model

`POST /api/v1/system/llm/pull`

Streams Ollama `/api/pull` progress as **application/x-ndjson** (one JSON object per line). The body defaults `provider` to `ollama`.

```json
{ "model": "qwen2.5:3b" }
```

**HTTP 200 does not mean the pull succeeded.** Treat the stream as successful only when a line contains `"status":"success"`. An `"error"` field or a connection drop without that line is a failure, even though the status code is 200.

Successful stream:

```text
{"status": "pulling manifest"}
{"status": "downloading", "completed": 50, "total": 100}
{"status": "success"}
```

Failed stream (still HTTP 200):

```text
{"status": "pulling manifest"}
{"error": "pull access denied"}
```

If Ollama cannot be reached before the stream opens, the API returns **503** with `LLM_UNAVAILABLE`. Wrong provider, model not in the installable set, or an invalid model name returns **422**.

After a successful pull, the server refreshes the Ollama catalog cache, so the new model shows up on `GET /system/llm/models` immediately (no need to wait 60 seconds or pass `refresh=true`).

Closing or cancelling the client's pull request cancels the upstream Ollama
request, closes its connection, and does not emit a success line or refresh the
catalog. Whether Ollama removes or reuses files from an interrupted download
has not been verified and remains to be checked.

## Delete an Ollama model

`DELETE /api/v1/system/llm/models`

```json
{ "model": "qwen2.5:3b" }
```

`provider` is optional and defaults to `ollama`. The model must pass the same
name and installable-model checks as a pull, and it must currently be installed.
The global default model, Ollama's provider default model, and a model with an
active pull cannot be deleted.

Success returns `200` and refreshes the Ollama catalog cache:

```json
{ "model": "qwen2.5:3b", "deleted": true }
```

The endpoint returns `404` (`LLM_MODEL_NOT_INSTALLED`) when Ollama does not
have the model, `409` (`LLM_MODEL_IN_USE`) when it is a default or its pull is
active, and `422` (`LLM_NOT_AVAILABLE`) for an invalid provider or model that
the server does not allow. Ollama connection failures and server errors return
`503` (`LLM_UNAVAILABLE`); other unexpected Ollama responses return
`502` (`LLM_BAD_RESPONSE`).

Active pull tracking is held in a lock-protected in-process set. In deployments
with multiple API processes, it is process-local and therefore only
authoritative for pulls handled by the same process.

## Test a model

`POST /api/v1/system/llm/test`

Sends a short prompt and checks the answer is valid JSON. The body is optional. Missing fields use the defaults.

```json
{ "provider": "ollama", "model": "llama3:8b" }
```

```json
{
  "provider": "ollama",
  "model": "llama3:8b",
  "ok": false,
  "latency_ms": 12,
  "detail": "Ollama has no model llama3:8b. Pull it with: ollama pull llama3:8b",
  "error_code": "LLM_MODEL_NOT_FOUND"
}
```

A failed test returns 200 with `ok: false`. A provider that is not enabled returns 422.

## Fill with a chosen model

`POST /api/v1/forms/fill` and `POST /api/v1/forms/jobs` take two optional fields:

| Field      | Meaning                                                                  |
| ---------- | ------------------------------------------------------------------------ |
| `provider` | One of the enabled providers. Defaults to `LLM_PROVIDER`.                |
| `model`    | A model that provider offers. Defaults to that provider's default model. |

The pair is checked before anything is stored or queued. For jobs, the provider and model are saved on the job and the worker checks them again.

## Health

`GET /api/v1/health` reports the default provider under `components.llm`. Use the models endpoint for the rest.

## Error codes

| Code                  | HTTP | Meaning                                                                |
| --------------------- | ---- | ---------------------------------------------------------------------- |
| `LLM_NOT_AVAILABLE`   | 422  | Provider not enabled, or model not in its list.                        |
| `LLM_CONFIG_ERROR`    | 500  | The LLM settings are wrong. The message names the setting and the fix. |
| `LLM_AUTH_FAILED`     | 502  | The provider rejected the API key.                                     |
| `LLM_MODEL_NOT_FOUND` | 502  | The provider has no such model.                                        |
| `LLM_MODEL_NOT_INSTALLED` | 404 | Ollama does not have the requested model installed. |
| `LLM_MODEL_IN_USE` | 409 | The Ollama model is a configured default or has an active pull. |
| `LLM_BAD_RESPONSE`    | 502  | The provider refused the request or did not return JSON.               |
| `LLM_UNAVAILABLE`     | 503  | Could not reach the provider, or it timed out.                         |
| `LLM_RATE_LIMITED`    | 503  | Still rate limited after retries, or out of quota.                     |
| `LLM_SECRET_KEY_UNAVAILABLE` | 503 | The API cannot read or create the credential-encryption master key. |
| `LLM_EXTERNAL_CONSENT_REQUIRED` | 422 | External-processing consent is required before saving a remote provider. |

Every error body has `error_code` and `message`. 503 responses add `retry_after_seconds`. Failed jobs store the same code and message in `error`.

## Deprecated

`GET /api/v1/forms/models` returns the default provider's model names only. Use `GET /api/v1/system/llm/models`.
