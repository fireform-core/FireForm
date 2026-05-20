# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FireForm is a "report once, file everywhere" tool for first responders: a single text/voice input is sent to a local LLM (Mistral via Ollama), extracted into JSON, and used to fill multiple agency PDF forms. Everything runs locally — no cloud dependencies, no PII leaves the machine. Recognized as a UN Digital Public Good.

## Architecture

Three-tier system glued together by Docker Compose:

1. **`api/`** — FastAPI service (port 8000). Two routers:
   - `routes/templates.py` — upload PDFs, run them through `commonforms` to create fillable templates, list/preview.
   - `routes/forms.py` — given a template id + free-form text, runs the extraction + fill pipeline and persists a `FormSubmission`.
   - Lifespan handler calls `init_db()` which creates SQLModel tables and seeds template id=2 (the "Manual Test Template" with the default employee fields). DB lives at `~/.fireform/fireform.db` (SQLite), **not** in the repo.
   - All exceptions in routes funnel through `api/errors/handlers.py` via `AppError`.

2. **`src/`** — The PDF-filling core, called from API routes via `src.controller.Controller`:
   - `controller.py` → `file_manipulator.py` → (`llm.py`, `filler.py`). Controller is the only entry point routes use; never reach into `filler`/`llm` from the API layer.
   - `llm.LLM.main_loop()` iterates *one Ollama call per field* using `prompt.txt` as the template, with retry/timeout. `OLLAMA_HOST` env var points at the Ollama service (default `http://localhost:11434`, set to `http://ollama:11434` inside Docker).
   - `filler.Filler.fill_form()` uses `pdfrw` and assigns answers to PDF widget annotations sorted **top-to-bottom, left-to-right by `Rect`** — answers in `LLM._json` are ordered to match. If you change field iteration order in `LLM`, you must change the sort in `Filler` or fills will misalign.
   - `file_manipulator.create_template()` calls `commonforms.prepare_form()`. `commonforms` pulls in `rfdetr` which tries to use CUDA; both `api/main.py` and `src/main.py` set `CUDA_VISIBLE_DEVICES=""` *and* monkey-patch `rfdetr.detr._ensure_model_on_device` to force CPU. **Keep these patches** — they exist because Mac Silicon / Docker has no NVIDIA drivers.

3. **`frontend/`** — Electron app (`electron.js`) loading a plain HTML/JS UI (`index.html`, `app.js`). In dev it assumes the backend is already running (Docker). In a packaged build it spawns a bundled `bin/api-backend` binary from `process.resourcesPath`. There is no bundler/transpiler — vanilla JS only.

### Important wiring details
- `PYTHONPATH=/app` (repo root) is required so imports like `from api.db...` and `from src.controller...` resolve. Set in `Dockerfile` and `docker-compose.yml`.
- The `Template.fields` column is a JSON dict (`{field_name: type_str}`). Iteration order of this dict determines the order answers are filled into the PDF.
- `_resolve_target_directory` / `_resolve_project_file` in `routes/templates.py` enforce that all upload/preview paths stay inside `PROJECT_ROOT`. Don't loosen these checks — the directory-traversal test in `tests/test_api.py` covers them.

## Commands

The Makefile is the canonical interface; `make help` prints the menu.

| Task | Command |
|------|---------|
| Build images, start containers, pull Mistral | `make fireform` |
| Start / stop only | `make up` / `make down` |
| Tail logs (all / one service) | `make logs` / `make logs-app` / `make logs-frontend` / `make logs-ollama` |
| Python shell inside app container | `make shell` |
| Run the full test suite | `make test` (= `docker compose exec app python3 -m pytest tests/ -v`) |
| Run a single test | `docker compose exec app python3 -m pytest tests/test_api.py::TestFormEndpoints::test_fill_form_success -v` |
| Pull Mistral into Ollama manually | `make pull-model` |
| Nuke containers + volumes | `make clean` (or `super-clean` for `docker system prune`) |

Services after `make up`: frontend at `http://localhost:5173`, API at `http://localhost:8000`, docs at `http://localhost:8000/docs`, Ollama at `http://localhost:11434`.

### Frontend (Electron desktop app)
```
cd frontend
npm install
npm start              # run Electron against the running backend
npm run dist           # build .dmg/.exe/.AppImage via electron-builder
```
The packaged app expects a `bin/api-backend` binary in `extraResources` — produced by the release workflow, not present in dev.

## Tests

`pytest` with `tests/conftest.py` providing `client`, `db`, `mock_controller`, and `pdf_upload` fixtures. Heavy deps (LLM, `commonforms`, filesystem) are **mocked** — tests do not require Ollama or a real PDF stack. When adding a route that calls `Controller`, extend `mock_controller` in `conftest.py` rather than hitting the real implementation.

## CI

`.github/workflows/` runs `tests.yml`, `lint.yml`, `docker-build.yml`, and `release.yml` (electron-builder, triggered by tags — see `frontend/package.json` `build` config).
