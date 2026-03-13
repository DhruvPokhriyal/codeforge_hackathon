// frontend/electron/main.js
// Electron Main Process — Digital Lifeboat
//
// Loads the frontend directly with no backend dependency.
// Security: contextIsolation=true, nodeIntegration=false.

const { app, BrowserWindow } = require('electron');
const path = require('path');

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width:     1400,
    height:    900,
    minWidth:  1100,
    minHeight: 700,
    title:     'Digital Lifeboat',
    webPreferences: {
      preload:          path.join(__dirname, 'preload.js'),
      contextIsolation: true,   // required for contextBridge
      nodeIntegration:  false,  // never expose Node to renderer
      sandbox:          false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));
  mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => { app.quit(); });

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

