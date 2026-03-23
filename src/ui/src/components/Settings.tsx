import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../config';
import type { SettingsData } from '../types';

// ── QR Code for mobile access ─────────────────────────────────────────────────
function MobileAccessCard({ settings }: { settings: SettingsData }) {
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Determine the LAN URL
  const { hostname, protocol } = window.location;
  const isLocal = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0';
  const port = settings.port;
  const lanUrl = isLocal
    ? null
    : `${protocol}//${hostname}${port && port !== 80 && port !== 443 ? `:${port}` : ''}`;

  // Generate QR code from a free API (requires desktop internet, not phone)
  useEffect(() => {
    if (!lanUrl) return;
    const encodedUrl = encodeURIComponent(lanUrl);
    setQrUrl(`https://api.qrserver.com/v1/create-qr-code/?size=160x160&format=png&color=3b82f6&bgcolor=ffffff&data=${encodedUrl}`);
  }, [lanUrl]);

  const serverAddress = `${settings.host === '0.0.0.0' ? 'your-computer-ip' : settings.host}:${settings.port}`;

  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">📱</span>
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Use on Your Phone</h3>
      </div>

      {lanUrl ? (
        <div className="flex flex-col sm:flex-row items-center gap-5">
          {/* QR Code */}
          <div className="flex-shrink-0">
            {qrUrl ? (
              <img
                src={qrUrl}
                alt="QR code to open DeskSearch on your phone"
                className="w-36 h-36 rounded-xl border border-gray-200 dark:border-dark-border"
                onError={() => setQrUrl(null)}
              />
            ) : (
              <canvas ref={canvasRef} className="w-36 h-36 rounded-xl bg-gray-100 dark:bg-dark-hover" />
            )}
          </div>
          <div className="space-y-2 text-center sm:text-left">
            <p className="text-sm text-gray-700 dark:text-gray-300 font-medium">
              Scan with your phone's camera
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Your phone needs to be on the same Wi-Fi network.
            </p>
            <div className="inline-flex items-center gap-2 bg-gray-50 dark:bg-dark-hover px-3 py-1.5 rounded-lg">
              <span className="text-xs font-mono text-gray-700 dark:text-gray-200 break-all">{lanUrl}</span>
              <button
                onClick={() => navigator.clipboard.writeText(lanUrl)}
                className="tap-sm text-gray-400 hover:text-accent-blue transition-colors flex-shrink-0"
                title="Copy URL"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            You're accessing DeskSearch from <strong>localhost</strong>. To use it on your phone:
          </p>
          <ol className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
            <li className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-accent-blue/10 text-accent-blue text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-semibold">1</span>
              <span>Make sure your phone is on the <strong>same Wi-Fi</strong> as this computer</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-accent-blue/10 text-accent-blue text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-semibold">2</span>
              <span>Find your computer's local IP address (usually starts with 192.168…)</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-accent-blue/10 text-accent-blue text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-semibold">3</span>
              <span>Open your phone's browser and go to: <code className="bg-gray-100 dark:bg-dark-hover px-1.5 py-0.5 rounded font-mono text-xs">{serverAddress}</code></span>
            </li>
          </ol>
          <p className="text-xs text-gray-400 dark:text-gray-500 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40 rounded-lg px-3 py-2">
            💡 If DeskSearch was started with <code className="font-mono">host: 0.0.0.0</code>, it's already accessible on your local network.
          </p>
        </div>
      )}
    </div>
  );
}

// ── File type selector ────────────────────────────────────────────────────────
const COMMON_TYPES = [
  { ext: '.pdf',  label: 'PDFs',          icon: '📄' },
  { ext: '.docx', label: 'Word documents', icon: '📄' },
  { ext: '.txt',  label: 'Text files',     icon: '📝' },
  { ext: '.md',   label: 'Notes (Markdown)', icon: '📝' },
  { ext: '.xlsx', label: 'Spreadsheets',   icon: '📊' },
  { ext: '.csv',  label: 'CSV data',       icon: '📊' },
  { ext: '.py',   label: 'Python scripts', icon: '🐍' },
  { ext: '.ipynb', label: 'Notebooks',     icon: '📓' },
  { ext: '.eml',  label: 'Emails',         icon: '✉️' },
  { ext: '.html', label: 'Web pages',      icon: '🌐' },
];

// ── Main Settings ─────────────────────────────────────────────────────────────
export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Editable fields
  const [chunkSize, setChunkSize] = useState('');
  const [chunkOverlap, setChunkOverlap] = useState('');
  const [maxFileSize, setMaxFileSize] = useState('');
  const [excludedDirs, setExcludedDirs] = useState('');
  const [fileExtensions, setFileExtensions] = useState<string[]>([]);
  const [customExtensions, setCustomExtensions] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/settings`);
        if (res.ok && active) {
          const data: SettingsData = await res.json();
          setSettings(data);
          setChunkSize(String(data.chunk_size));
          setChunkOverlap(String(data.chunk_overlap));
          setMaxFileSize(String(data.max_file_size_mb));
          setExcludedDirs(data.excluded_dirs.join(', '));
          setFileExtensions(data.file_extensions);
          // Custom extensions: those not in COMMON_TYPES
          const commonExts = COMMON_TYPES.map(t => t.ext);
          const custom = data.file_extensions.filter(e => !commonExts.includes(e));
          setCustomExtensions(custom.join(', '));
        }
      } catch {
        // ignore
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, []);

  const toggleExtension = (ext: string) => {
    setFileExtensions(prev =>
      prev.includes(ext) ? prev.filter(e => e !== ext) : [...prev, ext]
    );
  };

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const allExtensions = [...fileExtensions];
      // Add any custom extensions
      if (customExtensions.trim()) {
        const customs = customExtensions.split(',').map(s => {
          const t = s.trim();
          return t.startsWith('.') ? t : `.${t}`;
        }).filter(Boolean);
        customs.forEach(e => { if (!allExtensions.includes(e)) allExtensions.push(e); });
      }

      const body: Record<string, unknown> = {
        file_extensions: allExtensions,
      };

      if (showAdvanced) {
        const cs = parseInt(chunkSize);
        if (!isNaN(cs)) body.chunk_size = cs;
        const co = parseInt(chunkOverlap);
        if (!isNaN(co)) body.chunk_overlap = co;
        const mfs = parseInt(maxFileSize);
        if (!isNaN(mfs)) body.max_file_size_mb = mfs;
        if (excludedDirs.trim()) {
          body.excluded_dirs = excludedDirs.split(',').map(s => s.trim()).filter(Boolean);
        }
      }

      const res = await fetch(`${API_BASE_URL}/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setMessage({ type: 'success', text: 'Settings saved! Re-index your folders for changes to take effect.' });
      } else {
        const err = await res.json();
        setMessage({ type: 'error', text: err.detail || 'Couldn\'t save — please try again.' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Couldn\'t connect to DeskSearch. Is the app running?' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-6 space-y-5">
        <div className="h-7 bg-gray-200 dark:bg-dark-border rounded-lg w-36 animate-pulse" />
        {[1, 2, 3].map(i => (
          <div key={i} className="h-32 bg-gray-200 dark:bg-dark-border rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 px-4">
        <div className="w-12 h-12 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
          <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
          </svg>
        </div>
        <p className="text-gray-600 dark:text-gray-400 text-center">
          Couldn't load settings. Make sure DeskSearch is running.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-5 pb-10">
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">Settings</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Control what DeskSearch indexes and how it works.
        </p>
      </div>

      {/* Status message */}
      {message && (
        <div className={`text-sm px-4 py-3 rounded-xl flex items-start gap-2 ${
          message.type === 'success'
            ? 'bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800/40'
            : 'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800/40'
        }`}>
          <span>{message.type === 'success' ? '✅' : '⚠️'}</span>
          <span>{message.text}</span>
        </div>
      )}

      {/* What to index */}
      <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl p-5">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">What types of files to search</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Check the file types you want DeskSearch to include. Changes take effect when you refresh a folder.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {COMMON_TYPES.map(({ ext, label, icon }) => {
            const checked = fileExtensions.includes(ext);
            return (
              <label
                key={ext}
                className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  checked
                    ? 'border-accent-blue/40 bg-accent-blue/5 dark:bg-accent-blue/10'
                    : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-dark-hover'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleExtension(ext)}
                  className="w-4 h-4 rounded border-gray-300 text-accent-blue focus:ring-accent-blue/50 flex-shrink-0"
                />
                <span className="text-lg flex-shrink-0">{icon}</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-200">{label}</div>
                  <div className="text-xs text-gray-400 font-mono">{ext}</div>
                </div>
              </label>
            );
          })}
        </div>

        {/* Custom types */}
        <div className="mt-4">
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
            Other file types (optional)
          </label>
          <input
            type="text"
            value={customExtensions}
            onChange={(e) => setCustomExtensions(e.target.value)}
            placeholder="e.g. .rs, .toml, .r"
            className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono"
          />
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Separate with commas</p>
        </div>
      </div>

      {/* Mobile access */}
      <MobileAccessCard settings={settings} />

      {/* About */}
      <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">About this installation</h3>
        <div className="space-y-2.5">
          <InfoRow
            label="Model"
            value={settings.embedding_model}
            hint="The AI model used to understand your files"
          />
          <InfoRow
            label="Storage"
            value={settings.data_dir}
            hint="Where DeskSearch keeps its index data"
          />
          <InfoRow
            label="Server"
            value={`${settings.host}:${settings.port}`}
            hint="The address DeskSearch listens on"
          />
        </div>
      </div>

      {/* Advanced */}
      <div>
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="tap-sm flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
        >
          <svg className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          {showAdvanced ? 'Hide advanced settings' : 'Advanced settings'}
        </button>

        {showAdvanced && (
          <div className="mt-3 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl p-5 space-y-4 animate-slideDown">
            <p className="text-xs text-gray-500 dark:text-gray-400 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40 rounded-lg px-3 py-2">
              ⚠️ These settings affect how DeskSearch processes files. Changing them requires re-indexing your folders to take effect.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <AdvancedInput
                label="Chunk size"
                value={chunkSize}
                onChange={setChunkSize}
                hint="Characters per section (64–4096)"
              />
              <AdvancedInput
                label="Chunk overlap"
                value={chunkOverlap}
                onChange={setChunkOverlap}
                hint="Section overlap (0–512)"
              />
              <AdvancedInput
                label="Max file size"
                value={maxFileSize}
                onChange={setMaxFileSize}
                hint="Skip files larger than this (MB)"
                suffix="MB"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                Folders to skip
              </label>
              <textarea
                value={excludedDirs}
                onChange={(e) => setExcludedDirs(e.target.value)}
                rows={2}
                className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono resize-none"
                placeholder=".git, node_modules, .venv"
              />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Folder names to ignore during indexing, separated by commas</p>
            </div>
          </div>
        )}
      </div>

      {/* Save button */}
      <div className="flex items-center justify-between pt-2">
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Settings are saved locally and apply immediately.
        </p>
        <button
          onClick={save}
          disabled={saving}
          className="tap-sm flex items-center gap-2 px-5 py-2.5 text-sm rounded-xl bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-50 transition-colors font-medium"
        >
          {saving ? (
            <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Saving…</>
          ) : (
            <><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/></svg> Save Settings</>
          )}
        </button>
      </div>
    </div>
  );
}

function InfoRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 py-2 border-b border-gray-100 dark:border-dark-border last:border-0">
      <div>
        <div className="text-sm text-gray-600 dark:text-gray-300">{label}</div>
        {hint && <div className="text-xs text-gray-400 dark:text-gray-500">{hint}</div>}
      </div>
      <span className="text-gray-700 dark:text-gray-200 font-mono text-xs bg-gray-100 dark:bg-dark-hover px-2 py-1 rounded-lg break-all">{value}</span>
    </div>
  );
}

function AdvancedInput({ label, value, onChange, hint, suffix }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  suffix?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">{label}</label>
      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 ${suffix ? 'pr-10' : ''}`}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">{suffix}</span>
        )}
      </div>
      {hint && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}
