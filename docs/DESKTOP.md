# Desktop Production Deployment

FireForm ships as a self-contained desktop application for Windows, macOS, and Linux. The desktop build runs the entire stack locally — FastAPI backend, SQLite database, and Ollama LLM inference — without any external infrastructure or internet connection required after installation.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Electron Shell                     │
│  (renders React UI · manages process lifecycle)     │
├──────────────┬──────────────────────────────────────┤
│  api-backend │  Ollama (host-managed)               │
│  (PyInstaller│  127.0.0.1:11434                    │
│   binary)    │  model: qwen2.5:3b                   │
│  127.0.0.1   │                                      │
│  :8000       │                                      │
├──────────────┴──────────────────────────────────────┤
│  SQLite database (userData/data/fireform.db)        │
└─────────────────────────────────────────────────────┘
```

| Component | Technology | Notes |
|:---|:---|:---|
| Desktop shell | Electron | Renders existing React frontend |
| API backend | FastAPI + PyInstaller binary | `api-backend` / `api-backend.exe` |
| Database | SQLite (WAL mode) | No server process; file-per-user |
| Task queue | Celery (in-process, eager) | No Redis; runs in the API process |
| LLM inference | Ollama (host binary) | Auto-detected, started, or silently installed |
| Default model | `qwen2.5:3b` | Auto-pulled on first run |
| Voice input | Disabled | Whisper not bundled in desktop mode |

All services bind exclusively to `127.0.0.1` — no LAN exposure.

---

## Data Directories

The application stores all user data under the OS-standard user data directory:

| OS | Path |
|:---|:---|
| macOS | `~/Library/Application Support/FireForm/` |
| Windows | `%LOCALAPPDATA%\FireForm\` |
| Linux | `~/.config/FireForm/` |

Directory layout:

```
FireForm/
├── data/
│   └── fireform.db        ← SQLite database
├── secrets/
│   └── llm_secret.key     ← LLM API key (written by backend on first run)
└── uploads/               ← User-uploaded files (created on demand)
```

---

## First-Run Initialization

On the very first launch:

1. **Backend binary starts** — Electron spawns `api-backend` with `FIREFORM_DESKTOP=true` and the `userData` paths set via environment variables.
2. **Database initialized** — Alembic runs all migrations against `fireform.db`; the seed template is inserted.
3. **Ollama lifecycle** — Electron checks port `11434`:
   - If a process is already serving → use it.
   - If Ollama is installed but not running → start it silently (`ollama serve`).
   - If Ollama is not installed → download and install silently, then start it.
4. **Model provisioned** — Once Ollama is reachable, the renderer checks whether `qwen2.5:3b` is installed. If not, it triggers an automatic pull using the existing in-app download UI (progress toast visible to the user).

---

## CI Release Pipeline

Releases are built automatically in two stages:

### Stage 1 — Backend binary (`FireForm` repo)

Trigger: push a tag matching `v*` to `fireform-core/FireForm`.

Workflow: [`.github/workflows/build-desktop-binaries.yml`](../.github/workflows/build-desktop-binaries.yml)

```bash
git tag v2.0.0
git push origin v2.0.0
```

The workflow builds a PyInstaller binary on each platform runner:

| Platform | Runner | Output artifact |
|:---|:---|:---|
| macOS (arm64) | `macos-latest` | `api-backend-macos` |
| Linux (x86_64) | `ubuntu-latest` | `api-backend-linux` |
| Windows (x86_64) | `windows-latest` | `api-backend-windows` |

Binaries are attached to the GitHub Release matching the tag.

### Stage 2 — Electron installer (`fireform-frontend` repo)

Trigger: push the same `v*` tag to `fireform-core/fireform-frontend`.

Workflow: [`.github/workflows/release.yml`](https://github.com/fireform-core/fireform-frontend/blob/main/.github/workflows/release.yml)

The workflow:
1. Downloads the matching `api-backend-{platform}` asset from the `FireForm` release.
2. Places the binary in `bin/` so `electron-builder` picks it up via `extraResources`.
3. Builds platform-native installers with `electron-builder`.
4. Uploads installers to a GitHub Release on the frontend repo.

| Platform | Installer format |
|:---|:---|
| macOS | `.dmg` |
| Windows | NSIS `.exe` |
| Linux | `.AppImage` |

---

## Environment Variables

The Electron main process sets these before spawning the backend:

| Variable | Value | Purpose |
|:---|:---|:---|
| `FIREFORM_DESKTOP` | `true` | Enables desktop mode in the backend |
| `FIREFORM_DATA_DIR` | `{userData}/data` | Directory for the SQLite file and uploads |
| `DATABASE_URL` | `sqlite:///{userData}/data/fireform.db` | Database connection string |
| `LLM_SECRET_KEY_FILE` | `{userData}/secrets/llm_secret.key` | Path for the LLM key file |
| `PORT` | `8000` | Listening port for the FastAPI backend |

---

## Developer Setup

The Docker development stack is **unchanged**. Desktop mode is purely opt-in.

To run the backend in desktop mode locally (without Electron):

```bash
cd FireForm
FIREFORM_DESKTOP=true \
FIREFORM_DATA_DIR=/tmp/fireform-dev-data \
DATABASE_URL="sqlite:////tmp/fireform-dev-data/fireform.db" \
PORT=8000 \
./dist/api-backend
```

To build the backend binary locally:

```bash
cd FireForm
PYINSTALLER_CONFIG_DIR=./.pyinstaller_cache \
.venv/bin/pyinstaller fireform-backend.spec --noconfirm
# Output: dist/api-backend  (~70 MB)
```

To run the full Electron app in dev mode (backend not needed if using Docker):

```bash
cd fireform-frontend
npm install      # one-time
npm run dev      # opens Electron dev window pointing at localhost:5173
```

If you want to test the full desktop flow in dev mode (with the binary):

```bash
# After building dist/api-backend in the FireForm repo:
cp ../FireForm/dist/api-backend ./bin/api-backend
chmod +x ./bin/api-backend
npm run dev
```

---

## Security Notes

- All services (`FastAPI`, `Ollama`) bind to `127.0.0.1` only — no LAN or internet exposure.
- The SQLite database is stored in the OS user profile directory — not world-readable on standard OS permission models.
- Ollama model weights stay in the host-native Ollama model directory (not inside the app bundle).
- `FIREFORM_DESKTOP=true` disables Whisper — no microphone access is requested in desktop mode.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|:---|:---|:---|
| App launches but shows "Cannot reach backend" | Binary failed to start | Check Electron console logs (View → Toggle Dev Tools) |
| `GET /api/v1/health` returns degraded | Whisper check — expected | Whisper is disabled in desktop mode; health still returns `healthy` |
| Ollama model pull not triggered | Ollama not reachable within 30 s | Ensure Ollama app is not blocked by firewall; relaunch app |
| Database error on startup | Corrupted or locked `.db` file | Delete `{userData}/data/fireform.db` to reset (data loss) |
| `api-backend` permission denied on Linux | Binary not executable | `chmod +x bin/api-backend` |
