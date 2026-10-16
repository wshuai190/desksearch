const { app, BrowserWindow, globalShortcut, Tray, Menu, nativeImage } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const os = require('os');

const DEFAULT_BACKEND_HOST = '127.0.0.1';
const DEFAULT_BACKEND_PORT = 3777;

/**
 * The backend takes its host/port from <data_dir>/config.json, so the window
 * must resolve them from the same source. Assuming 3777 made the UI load a
 * dead URL whenever the user had changed the port (blank window).
 */
function resolveDataDir() {
  return process.env.DESKSEARCH_DATA_DIR || path.join(os.homedir(), '.desksearch');
}

function readBackendConfig() {
  try {
    // Strip a UTF-8 BOM: Windows PowerShell 5.1 adds one, and JSON.parse
    // rejects it just like Python's json.load does.
    const raw = fs.readFileSync(path.join(resolveDataDir(), 'config.json'), 'utf8');
    return JSON.parse(raw.replace(/^\uFEFF/, ''));
  } catch {
    return {};
  }
}

const _config = readBackendConfig();

function pickNumber(value, fallback, min, max) {
  const n = Number(value);
  return Number.isInteger(n) && n >= min && n <= max ? n : fallback;
}

const BACKEND_PORT = process.env.DESKSEARCH_PORT
  ? pickNumber(process.env.DESKSEARCH_PORT, DEFAULT_BACKEND_PORT, 1, 65535)
  : pickNumber(_config.port, DEFAULT_BACKEND_PORT, 1, 65535);
const BACKEND_HOST =
  typeof _config.host === 'string' && _config.host.trim()
    ? _config.host.trim()
    : DEFAULT_BACKEND_HOST;
// The window always talks to loopback; an 0.0.0.0 bind still accepts it and
// keeps the "open on your phone" feature working.
const UI_HOST = BACKEND_HOST === '0.0.0.0' || BACKEND_HOST === '::' ? DEFAULT_BACKEND_HOST : BACKEND_HOST;
const BACKEND_URL = `http://${UI_HOST}:${BACKEND_PORT}`;

let mainWindow = null;
let tray = null;
let backendProcess = null;
let isQuitting = false;
let backendLog = [];
let startupRetry = null;

function recordBackendLog(line) {
  const text = String(line).trim();
  if (!text) return;
  for (const entry of text.split('\n')) {
    backendLog.push(entry);
  }
  if (backendLog.length > 40) backendLog = backendLog.slice(-40);
}

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

/** Human-readable page shown while the backend is down (never a blank window). */
function showStartupPage(heading, detail) {
  if (!mainWindow) return;
  const log = backendLog.slice(-12).join('\n');
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>DeskSearch</title>
<style>
  :root { color-scheme: dark light; }
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
         background:#0a0a0a; color:#e5e7eb;
         font:14px/1.6 "Segoe UI", -apple-system, "Microsoft YaHei", sans-serif; }
  .card { max-width:640px; padding:32px 36px; }
  h1 { font-size:20px; margin:0 0 12px; }
  p  { margin:0 0 10px; color:#9ca3af; }
  code { background:#161b22; padding:2px 6px; border-radius:6px; color:#d1d5db; }
  pre { background:#111827; padding:12px 14px; border-radius:10px; overflow:auto; max-height:220px;
        font-size:12px; color:#9ca3af; white-space:pre-wrap; }
  button { margin-top:16px; padding:8px 18px; border-radius:10px; border:1px solid #374151;
           background:#1f2937; color:#e5e7eb; cursor:pointer; font-size:13px; }
</style></head><body><div class="card">
  <h1>${heading}</h1>
  <p>${detail}</p>
  <p>后端地址：<code>${BACKEND_URL}</code></p>
  ${log ? `<p>后端日志（末尾）：</p><pre>${log.replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' })[c])}</pre>` : ''}
  <button onclick="location.reload()">重试</button>
</div></body></html>`;
  mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
}

function startBackend() {
  // PyInstaller appends .exe on Windows — the bundled binary must be resolved
  // with the platform's executable suffix or the backend never launches.
  const exeName =
    process.platform === 'win32' ? 'desksearch-backend.exe' : 'desksearch-backend';

  // Find the bundled backend binary
  let backendPath;
  if (app.isPackaged) {
    // In packaged app: backend is in Resources/backend/
    backendPath = path.join(process.resourcesPath, 'backend', exeName);
  } else {
    // In development: use dist from PyInstaller build
    backendPath = path.join(__dirname, '..', 'dist', 'desksearch-backend', exeName);
  }

  if (!fs.existsSync(backendPath)) {
    recordBackendLog(`Binary not found at: ${backendPath}`);
    console.error(`[backend] Binary not found at: ${backendPath}`);
    return;
  }

  console.log(`[backend] Starting: ${backendPath} (${BACKEND_HOST}:${BACKEND_PORT})`);

  // Pass host/port explicitly: the window and the server then cannot disagree,
  // even if the config file changes between launches.
  backendProcess = spawn(
    backendPath,
    ['serve', '--no-browser', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)],
    {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
    },
  );

  backendProcess.stdout.on('data', (data) => {
    recordBackendLog(data.toString());
    console.log(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    recordBackendLog(data.toString());
    console.error(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.on('error', (err) => {
    recordBackendLog(`Failed to start backend: ${err.message}`);
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
  // Superseded by waitForBackendThenLoad(), which keeps the window interactive
  // and reports failures instead of resolving silently.
  return Promise.resolve();
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

/**
 * Keep polling until the backend answers, then hand the window over to the real
 * UI. Long first runs (index migration, model download) no longer end in a
 * broken window: the user sees progress until the app is actually ready.
 */
function waitForBackendThenLoad(retries = 90, interval = 1000) {
  let attempts = 0;

  const tick = () => {
    if (isQuitting) return;
    attempts++;
    const req = http.get(`${BACKEND_URL}/api/status`, (res) => {
      res.resume();
      if (res.statusCode === 200) {
        console.log(`[startup] backend ready after ${attempts}s — loading UI`);
        mainWindow.loadURL(BACKEND_URL);
        return;
      }
      retry();
    });
    req.on('error', retry);
    req.setTimeout(2000, () => {
      req.destroy();
      retry();
    });
  };

  const retry = () => {
    if (isQuitting) return;
    if (attempts >= retries) {
      console.error('[startup] backend did not become ready in time');
      showStartupPage(
        'DeskSearch 后端启动超时',
        '后端进程尚未就绪。首次启动可能正在迁移索引或下载模型，请稍候再点「重试」。',
      );
      // Keep trying in the background — the window switches over by itself.
      startupRetry = setTimeout(() => waitForBackendThenLoad(retries, interval), 5000);
      return;
    }
    startupRetry = setTimeout(tick, interval);
  };

  tick();
}

app.whenReady().then(() => {
  startBackend();
  createTray();
  registerShortcuts();

  // Show the window immediately with a status page; it is replaced by the real
  // UI as soon as the backend answers.
  createWindow();
  showStartupPage('DeskSearch 正在启动…', '正在等待本地搜索服务就绪（首次启动可能稍久）。');

  waitForBackendThenLoad();

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
  if (startupRetry) clearTimeout(startupRetry);
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
