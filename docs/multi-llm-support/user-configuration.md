# Local provider configuration

The following endpoints configure provider credentials and model IDs for one
FireForm installation:

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/system/llm/providers/config` | Read provider configuration status; never returns full API keys |
| `PUT /api/v1/system/llm/providers/config/{provider}` | Save an API key and, for `custom`, a base URL and structured-output option |
| `DELETE /api/v1/system/llm/providers/config/{provider}` | Remove the provider configuration and its manually added models |
| `POST /api/v1/system/llm/providers/config/{provider}/validate` | Test candidate credentials without saving them |
| `POST /api/v1/system/llm/providers/config/{provider}/models` | Test a model ID with a generation request and save it when successful |
| `DELETE /api/v1/system/llm/providers/config/{provider}/models` | Remove a manually added model ID |
| `GET /api/v1/system/llm/external-consent` | Read the installation-wide external-processing consent |
| `PUT /api/v1/system/llm/external-consent` | Change that consent |

The `provider` path value is `openai`, `gemini`, `anthropic`, or `custom`.
Ollama continues to be configured through its local service settings. A saved
credential takes precedence over the corresponding environment key. A
manually entered model ID is checked by sending a short test generation; it is
then included in `/api/v1/system/llm/models` with `"manual": true`. For custom
OpenAI-compatible servers, manual entry is the usual route when the server
does not expose a compatible model-list endpoint.

## Master-key lifecycle

If `LLM_SECRET_KEY` is set in the API and worker environments, it takes
precedence. Otherwise, when the API first saves a credential, it generates a
Fernet key and creates `LLM_SECRET_KEY_FILE` with exclusive creation and
restrictive permissions. The worker reads that file from the shared persistent
`llm_secrets` Docker volume; it never creates the key. The default container
path is `/data/secrets/llm_secret.key`. An unreadable or invalid key means saved
credentials are ignored and reported as unavailable rather than crashing the
worker. If the configured default provider depends on such a credential and
Ollama is enabled, FireForm falls back to Ollama.

Back up the generated key securely and separately from the database. A
database-only backup cannot decrypt saved provider credentials without the
master key. This is not protection from someone who can access the machine or
the running containers: that person may be able to read the key file and
credentials. If `docker compose down -v` removes the `llm_secrets` volume, the
saved encrypted credentials become unusable; provide the keys again through
the configuration interface. Restoring the volume/key is required to restore
the existing credentials.

## Limitations and deployment safety

This is a **local, single-user** configuration feature, not user-account
management. The provider configuration, manual models, and external-processing
consent are global to the installation. The configuration routes do not have
authentication, and the Compose app port is published on `0.0.0.0:8000` by
default. For a local-only installation, bind the app port to loopback, for
example `127.0.0.1:8000:8000`, and do not expose it to an untrusted network.

Before deploying this design as a multi-user client-server service, it would
need at least:

- authentication and authorization for configuration and model routes;
- credentials and manually selected models scoped to each user;
- external-processing consent set by an authorized administrator, rather than
  a global user-controlled flag;
- an authorized credential reference attached to jobs (never the key itself);
- a registry/cache scoped to the authenticated user;
- strict custom-URL policy and network-level egress controls; and
- managed master-key provisioning, rotation, backup, and recovery.

Custom URL validation rejects malformed URLs and embedded credentials, but it
is **not complete SSRF protection**. DNS changes, rebinding, redirects, and
network routing can still make an apparently acceptable hostname reach an
unintended destination. Do not accept arbitrary custom URLs from untrusted
clients.

The consent flag only gates calls to external providers; it is not an
authentication boundary. A custom local server does not require external
consent. From inside Docker, address a server on the host as
`http://host.docker.internal:<port>/v1` (not `localhost`); use a service name
for another Compose service.

Only the full API key is secret: API responses expose status metadata and, when
available, a last-four-character hint. Keys are encrypted in the database and
are not included in validation errors or logs. `LLM_SECRET_KEY_UNAVAILABLE`
means the API could not read or create the master key; the worker treats an
unreadable saved credential as unconfigured and logs a warning.

The `LLM_EXTERNAL_CONSENT_REQUIRED` error is HTTP 422 and blocks saving a
remote provider or custom URL until consent is enabled. A failure to access the
master key is HTTP 503 with `LLM_SECRET_KEY_UNAVAILABLE`.
