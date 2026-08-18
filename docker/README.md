# Docker

```
docker/
  dev/
    Dockerfile        # uvicorn --reload, source-mounted for hot reload
    compose.yml
  prod/
    Dockerfile        # multi-stage build, gunicorn, no source mount
    compose.yml
  .env.example        # template — copy to .env.dev or .env.prod
  .env.dev            # gitignored, dev values
  .env.prod           # gitignored, prod values
  entrypoint.sh       # runs DB migrations then exec's the server command
  README.md
```

## Env vars

See `.env.example` for the full list with descriptions.

Both compose files load the env file into the app and worker containers with an
`env_file` block, so a setting added to `.env.dev` or `.env.prod` reaches the
running code without being listed a second time. The `environment` block below
it still wins, and it is there for the handful of values a container needs
different from the host, such as service names and data directories.

`--env-file` on the compose command line is a separate thing. It only fills in
`${}` placeholders inside the compose file and puts nothing into the container.

## Volumes

`docker compose down` never removes volumes. Use `docker compose down -v` only to intentionally wipe all data.

| Volume             | Path in container      | Purpose                             |
| ------------------ | ---------------------- | ----------------------------------- |
| `fireform_db`      | `/data/db/fireform.db` | SQLite database                     |
| `fireform_uploads` | `/data/uploads`        | Uploaded templates + generated PDFs |
| `ollama_data`      | `/root/.ollama`        | Ollama model weights                |
| `whisper_models`   | `/data/whisper`        | Whisper model cache                 |
