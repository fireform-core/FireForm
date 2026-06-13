const { app, BrowserWindow } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let backendProcess = null;

function startBackend() {
  if (app.isPackaged) {
    const ext = process.platform === 'win32' ? '.exe' : '';
    const backendPath = path.join(process.resourcesPath, "bin", `api-backend${ext}`);
    
    backendProcess = spawn(backendPath, [], {
      stdio: 'ignore'
    });

    backendProcess.on('error', (err) => {
      console.error('Failed to start backend process.', err);
    });
  } else {
    console.log("Running in development mode. Assuming backend is running via Docker Desktop.");
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1100,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });

  // Allow microphone capture for the local speech-to-text recorder. Audio is
  // only ever sent to the local Whisper service — nothing leaves the machine.
  win.webContents.session.setPermissionRequestHandler(
    (webContents, permission, callback) => {
      callback(permission === "media");
    }
  );

  win.loadFile("index.html");
  if (!app.isPackaged) {
    win.webContents.openDevTools();
  }
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
});

app.on("will-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
