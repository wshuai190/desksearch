import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { SettingsData } from '../types';

export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Editable fields
  const [chunkSize, setChunkSize] = useState('');
  const [chunkOverlap, setChunkOverlap] = useState('');
  const [maxFileSize, setMaxFileSize] = useState('');
  const [excludedDirs, setExcludedDirs] = useState('');
  const [fileExtensions, setFileExtensions] = useState('');

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
          setFileExtensions(data.file_extensions.join(', '));
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

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const body: Record<string, unknown> = {};
      const cs = parseInt(chunkSize);
      if (!isNaN(cs) && cs >= 64 && cs <= 4096) body.chunk_size = cs;
      const co = parseInt(chunkOverlap);
      if (!isNaN(co) && co >= 0 && co <= 512) body.chunk_overlap = co;
      const mfs = parseInt(maxFileSize);
      if (!isNaN(mfs) && mfs >= 1 && mfs <= 1024) body.max_file_size_mb = mfs;
      if (excludedDirs.trim()) {
        body.excluded_dirs = excludedDirs.split(',').map(s => s.trim()).filter(Boolean);
      }
      if (fileExtensions.trim()) {
        body.file_extensions = fileExtensions.split(',').map(s => s.trim()).filter(Boolean);
      }

      const res = await fetch(`${API_BASE_URL}/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setMessage({ type: 'success', text: 'Settings saved' });
      } else {
        const err = await res.json();
        setMessage({ type: 'error', text: err.detail || 'Failed to save' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
        <div className="h-6 bg-gray-200 dark:bg-dark-border rounded w-32 animate-pulse" />
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="space-y-2 animate-pulse">
            <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-24" />
            <div className="h-9 bg-gray-200 dark:bg-dark-border rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-400">Failed to load settings</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Settings</h2>

      {message && (
        <div className={`text-sm px-3 py-2 rounded-lg ${
          message.type === 'success'
            ? 'bg-green-500/10 text-green-500'
            : 'bg-red-500/10 text-red-500'
        }`}>
          {message.text}
        </div>
      )}

      <div className="space-y-4">
        {/* Read-only info */}
        <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">System Info</h3>
          <InfoRow label="Data Directory" value={settings.data_dir} />
          <InfoRow label="Embedding Model" value={settings.embedding_model} />
          <InfoRow label="Server" value={`${settings.host}:${settings.port}`} />
        </div>

        {/* Editable settings */}
        <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4 space-y-4">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Indexing Configuration</h3>

          <div className="grid grid-cols-2 gap-4">
            <SettingInput label="Chunk Size" value={chunkSize} onChange={setChunkSize} hint="64-4096 chars" />
            <SettingInput label="Chunk Overlap" value={chunkOverlap} onChange={setChunkOverlap} hint="0-512 chars" />
            <SettingInput label="Max File Size (MB)" value={maxFileSize} onChange={setMaxFileSize} hint="1-1024 MB" />
          </div>

          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Excluded Directories</label>
            <textarea
              value={excludedDirs}
              onChange={(e) => setExcludedDirs(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono"
              placeholder=".git, node_modules, .venv"
            />
          </div>

          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">File Extensions</label>
            <textarea
              value={fileExtensions}
              onChange={(e) => setFileExtensions(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono"
              placeholder=".txt, .md, .pdf, .py"
            />
          </div>
        </div>

        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 text-sm rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-gray-900 dark:text-white font-mono text-xs">{value}</span>
    </div>
  );
}

function SettingInput({ label, value, onChange, hint }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
}) {
  return (
    <div>
      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50"
      />
      {hint && <div className="text-xs text-gray-400 mt-0.5">{hint}</div>}
    </div>
  );
}
