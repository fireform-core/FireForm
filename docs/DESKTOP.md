# Desktop App

FireForm is available as a native desktop application powered by [Electron](https://www.electronjs.org/). It wraps the existing web frontend — no separate codebase, no framework migration.

## Download

Grab the latest installer from the **[Releases](https://github.com/fireform-core/FireForm/releases)** page:

| Platform | Format | File |
| :--- | :--- | :--- |
| macOS | DMG | `FireForm-x.x.x-arm64.dmg` |
| Windows | NSIS installer | `FireForm Setup x.x.x.exe` |
| Linux | AppImage | `FireForm-x.x.x.AppImage` |

## Run from Source

```bash
cd frontend
npm install    # one-time
npm start      # opens the desktop window
```

> **Note:** The backend (FastAPI + Ollama) must be running separately. See [DEPLOYMENT](DEPLOYMENT.md) or run `make fireform`.

## How It Works

The desktop app is intentionally minimal:

```
frontend/
├── index.html      ← existing UI (unchanged)
├── app.js          ← existing logic (unchanged)
├── styles.css      ← existing styles (unchanged)
├── electron.js     ← Electron main process (~25 lines)
├── preload.js      ← placeholder for future Node.js bridges
└── package.json    ← Electron + electron-builder config
```

- `electron.js` creates a `BrowserWindow` and loads `index.html`. That's it.
- `preload.js` is empty — ready for future use if Node.js APIs need to be exposed to the renderer.
- `package.json` contains `electron-builder` configuration for packaging installers.

## Releases (CI)

Releases are built automatically by GitHub Actions. Pushing a version tag triggers the pipeline:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The **[release.yml](https://github.com/fireform-core/FireForm/blob/main/.github/workflows/release.yml)** workflow:

1. Runs on **macOS**, **Windows**, and **Ubuntu** runners in parallel.
2. Installs dependencies with `npm ci`.
3. Builds installers with `electron-builder`.
4. Uploads artifacts to a GitHub Release matching the tag.

No secrets need to be configured — `GITHUB_TOKEN` is provided automatically.
