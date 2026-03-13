// frontend/electron/main.js
// Electron Main Process — Digital Lifeboat
//
// Responsibilities:
//   - Spawn FastAPI backend (python backend/main.py)
//   - Poll GET /health until backend is ready
//   - Create the BrowserWindow only after backend is healthy
//   - Tear down backend process on app quit
//   - Security: contextIsolation=true, nodeIntegration=false.
//
const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow = null;
let backendProcess = null;

const API_HOST = process.env.DL_API_HOST || '127.0.0.1';
const API_PORT = Number(process.env.DL_API_PORT || 8000);

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: 'Digital Lifeboat',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, // required for contextBridge
      nodeIntegration: false, // never expose Node to renderer
      sandbox: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startBackend() {
  if (backendProcess) return backendProcess;

  const backendEntry = path.join(__dirname, '..', '..', 'backend', 'main.py');

  backendProcess = spawn('python', [backendEntry], {
    cwd: path.join(__dirname, '..', '..'),
    env: {
      ...process.env,
      DL_API_HOST: API_HOST,
      DL_API_PORT: String(API_PORT),
    },
    stdio: 'ignore',
  });

  backendProcess.on('exit', () => {
    backendProcess = null;
    if (!app.isQuitting) {
      app.quit();
    }
  });

  return backendProcess;
}

function waitForHealth(maxWaitMs = 30000, intervalMs = 500) {
  const start = Date.now();

  return new Promise((resolve, reject) => {
    function checkOnce() {
      const req = http.get(
        {
          host: API_HOST,
          port: API_PORT,
          path: '/health',
          timeout: 2000,
        },
        (res) => {
          if (res.statusCode === 200) {
            res.resume();
            resolve(true);
          } else {
            res.resume();
            retry();
          }
        },
      );

      req.on('error', retry);
      req.on('timeout', () => {
        req.destroy();
        retry();
      });
    }

    function retry() {
      if (Date.now() - start > maxWaitMs) {
        reject(new Error('Backend health check timed out'));
        return;
      }
      setTimeout(checkOnce, intervalMs);
    }

    checkOnce();
  });
}

async function bootApp() {
  try {
    startBackend();
    await waitForHealth();
  } catch (err) {
    console.error('Failed to start backend:', err);
  } finally {
    createWindow();
  }
}

app.whenReady().then(bootApp);

app.on('window-all-closed', () => {
  app.isQuitting = true;
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  app.quit();
});

app.on('before-quit', () => {
  app.isQuitting = true;
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

