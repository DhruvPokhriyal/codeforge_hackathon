// frontend/electron/main.js
// Electron Main Process
//
// Responsibilities:
//   1. Spawn the FastAPI backend (python backend/main.py)
//   2. Poll GET /health every 500ms until 200 OK
//   3. Create the browser window and load frontend/index.html
//   4. Kill the backend process cleanly on app.quit
//
// Security: webPreferences enforces contextIsolation + no nodeIntegration.
// All IPC is channeled through preload.js (contextBridge).

const { app, BrowserWindow } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')

const API_BASE = 'http://127.0.0.1:8000'
let backendProcess = null
let mainWindow = null

// ── Launch Python backend ────────────────────────────────────────────────────
function startBackend() {
  const backendPath = path.join(__dirname, '..', '..', 'backend', 'main.py')
  backendProcess = spawn('python', [backendPath], {
    cwd: path.join(__dirname, '..', '..', 'backend'),
    stdio: 'inherit',
  })
  backendProcess.on('error', (err) => {
    console.error('[Backend] Failed to start:', err.message)
  })
  backendProcess.on('exit', (code) => {
    console.log(`[Backend] Exited with code ${code}`)
  })
}

// ── Poll /health until backend is ready ──────────────────────────────────────
function waitForBackend(onReady) {
  const check = () => {
    http.get(`${API_BASE}/health`, (res) => {
      if (res.statusCode === 200) {
        onReady()
      } else {
        setTimeout(check, 500)
      }
    }).on('error', () => setTimeout(check, 500))
  }
  check()
}

// ── Create the main browser window ───────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    title: 'Emergency Intelligence Hub',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,      // required for contextBridge
      nodeIntegration: false,      // never expose Node to renderer
      sandbox: false,
    },
  })
  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'))
  mainWindow.on('closed', () => { mainWindow = null })
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  startBackend()
  waitForBackend(() => {
    createWindow()
  })
})

app.on('window-all-closed', () => {
  if (backendProcess) backendProcess.kill()
  app.quit()
})

app.on('before-quit', () => {
  if (backendProcess) backendProcess.kill()
})
