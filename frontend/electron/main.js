// frontend/electron/main.js
// Electron Main Process — ARIA
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
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow = null;
let backendProcess = null;

const API_HOST = process.env.DL_API_HOST || '127.0.0.1';
const API_PORT = Number(process.env.DL_API_PORT || 8000);

const isDev = !app.isPackaged;

function resolveDevPythonCommand(projectRoot) {
  const isWindows = process.platform === 'win32';
  const venvPython = path.join(
    projectRoot,
    'backend',
    'venv',
    isWindows ? 'Scripts' : 'bin',
    isWindows ? 'python.exe' : 'python',
  );

  if (fs.existsSync(venvPython)) {
    return venvPython;
  }

  // Fallback to PATH executables if local venv is not present.
  return isWindows ? 'python' : 'python3';
}

function resolvePackagedPythonCommand() {
  // In packaged mode, we bundle the entire backend (including its venv)
  // under process.resourcesPath/backend. Use that Python interpreter.
  const resourcesRoot = process.resourcesPath;
  const isWindows = process.platform === 'win32';

  const candidate = path.join(
    resourcesRoot,
    'backend',
    'venv',
    isWindows ? 'Scripts' : 'bin',
    isWindows ? 'python.exe' : 'python',
  );

  if (fs.existsSync(candidate)) {
    return candidate;
  }

  throw new Error(`Packaged Python interpreter not found at: ${candidate}`);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: 'ARIA',
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

  let backendEntry;
  let pythonCmd;
  let cwd;

  if (isDev) {
    const projectRoot = path.join(__dirname, '..', '..');
    backendEntry = path.join(projectRoot, 'backend', 'main.py');
    pythonCmd = resolveDevPythonCommand(projectRoot);
    cwd = projectRoot;
  } else {
    const resourcesRoot = process.resourcesPath;
    const backendRoot = path.join(resourcesRoot, 'backend');
    backendEntry = path.join(backendRoot, 'main.py');
    pythonCmd = resolvePackagedPythonCommand();
    cwd = backendRoot;
  }

  backendProcess = spawn(pythonCmd, [backendEntry], {
    cwd,
    env: {
      ...process.env,
      DL_API_HOST: API_HOST,
      DL_API_PORT: String(API_PORT),
    },
    stdio: 'pipe',
  });

  backendProcess.stdout?.on('data', (chunk) => {
    process.stdout.write(`[backend] ${chunk}`);
  });

  backendProcess.stderr?.on('data', (chunk) => {
    process.stderr.write(`[backend] ${chunk}`);
  });

  backendProcess.on('error', (err) => {
    console.error('Failed to spawn backend process:', err);
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
    const backendAlreadyRunning = await waitForHealth(1500, 300)
      .then(() => true)
      .catch(() => false);

    if (!backendAlreadyRunning) {
      startBackend();
    }

    await waitForHealth(90000, 1000);
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

