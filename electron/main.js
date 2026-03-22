const { app, BrowserWindow, globalShortcut, Tray, Menu, nativeImage } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = 3777;
const BACKEND_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`;

let mainWindow = null;
let tray = null;
let backendProcess = null;
let isQuitting = false;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 500,
    titleBarStyle: 'default',
    backgroundColor: '#0a0a0a',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
      if (process.platform === 'darwin') {
        app.dock.hide();
      }
    }
  });

  mainWindow.loadURL(BACKEND_URL);
}

function startBackend() {
  const fs = require('fs');

  // Find the bundled backend binary
  let backendPath;
  if (app.isPackaged) {
    // In packaged app: backend is in Resources/backend/
    backendPath = path.join(process.resourcesPath, 'backend', 'desksearch-backend');
  } else {
    // In development: use dist from PyInstaller build
    backendPath = path.join(__dirname, '..', 'dist', 'desksearch-backend', 'desksearch-backend');
  }

  if (!fs.existsSync(backendPath)) {
    console.error(`[backend] Binary not found at: ${backendPath}`);
    return;
  }

  console.log(`[backend] Starting: ${backendPath}`);

  backendProcess = spawn(backendPath, ['serve', '--no-browser'], {
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.on('error', (err) => {
    console.error('Failed to start backend:', err.message);
  });

  backendProcess.on('exit', (code) => {
    console.log(`Backend exited with code ${code}`);
    if (!isQuitting) {
      console.log('Backend crashed, restarting in 2s...');
      setTimeout(startBackend, 2000);
    }
  });
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill('SIGTERM');
    setTimeout(() => {
      if (backendProcess && !backendProcess.killed) {
        backendProcess.kill('SIGKILL');
      }
    }, 3000);
  }
}

function waitForBackend(retries = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    function check() {
      attempts++;
      const req = http.get(`${BACKEND_URL}/api/status`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else if (attempts < retries) {
          setTimeout(check, interval);
        } else {
          reject(new Error('Backend did not respond with 200'));
        }
      });

      req.on('error', () => {
        if (attempts < retries) {
          setTimeout(check, interval);
        } else {
          reject(new Error('Backend did not start in time'));
        }
      });

      req.setTimeout(1000, () => {
        req.destroy();
        if (attempts < retries) {
          setTimeout(check, interval);
        } else {
          reject(new Error('Backend connection timed out'));
        }
      });
    }

    check();
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'tray-icon.png');
  let icon;
  try {
    icon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  } catch {
    icon = nativeImage.createEmpty();
  }

  tray = new Tray(icon);
  tray.setToolTip('DeskSearch');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open DeskSearch',
      click: showWindow,
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('click', showWindow);
}

function showWindow() {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
    if (process.platform === 'darwin') {
      app.dock.show();
    }
  }
}

function toggleWindow() {
  if (mainWindow && mainWindow.isVisible() && mainWindow.isFocused()) {
    mainWindow.hide();
    if (process.platform === 'darwin') {
      app.dock.hide();
    }
  } else {
    showWindow();
  }
}

function registerShortcuts() {
  globalShortcut.register('CommandOrControl+Shift+Space', toggleWindow);
}

app.whenReady().then(async () => {
  startBackend();
  createTray();
  registerShortcuts();

  try {
    await waitForBackend();
  } catch (err) {
    console.error('Backend startup failed:', err.message);
  }

  createWindow();

  app.on('activate', () => {
    if (mainWindow === null) {
      createWindow();
    } else {
      showWindow();
    }
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  stopBackend();
});

app.on('before-quit', () => {
  isQuitting = true;
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
