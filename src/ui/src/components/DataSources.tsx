import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { ConnectorInfo, ConnectorSyncResult } from '../types';

const CONNECTOR_ICONS: Record<string, string> = {
  'browser-bookmarks': '🔖',
  'clipboard-monitor': '📋',
  'email-connector': '✉️',
  'local-files': '📁',
  'slack-export': '💬',
};

const CONNECTOR_CONFIG_FIELDS: Record<string, { label: string; key: string; type: 'text' | 'textarea'; placeholder: string; help?: string }[]> = {
  'email-connector': [
    { label: 'Email directories', key: 'directories', type: 'textarea', placeholder: '/path/to/emails\n/path/to/mbox-files', help: 'One directory per line containing .eml or .mbox files' },
  ],
  'local-files': [
    { label: 'Directories to scan', key: 'directories', type: 'textarea', placeholder: '/path/to/documents\n/path/to/notes', help: 'One directory per line' },
    { label: 'File extensions', key: 'extensions', type: 'text', placeholder: '.txt, .md, .pdf', help: 'Comma-separated (leave empty for defaults)' },
    { label: 'Max file size (MB)', key: 'max_file_size_mb', type: 'text', placeholder: '50' },
  ],
  'slack-export': [
    { label: 'Export path', key: 'export_path', type: 'text', placeholder: '/path/to/slack-export or /path/to/export.zip', help: 'Path to extracted Slack export directory or ZIP file' },
    { label: 'Include bot messages', key: 'include_bots', type: 'text', placeholder: 'false', help: 'Set to "true" to include bot messages' },
  ],
  'browser-bookmarks': [
    { label: 'Chrome bookmarks path', key: 'chrome_bookmarks', type: 'text', placeholder: '(auto-detected)', help: 'Override the default Chrome bookmarks path' },
    { label: 'Firefox places path', key: 'firefox_places', type: 'text', placeholder: '(auto-detected)', help: 'Override the default Firefox places.sqlite path' },
  ],
};

function ConnectorCard({
  connector,
  onSync,
  onSave,
}: {
  connector: ConnectorInfo;
  onSync: (name: string) => Promise<ConnectorSyncResult | null>;
  onSave: (name: string, config: Record<string, unknown>) => Promise<boolean>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<ConnectorSyncResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});

  const icon = CONNECTOR_ICONS[connector.name] || '🔌';
  const fields = CONNECTOR_CONFIG_FIELDS[connector.name] || [];

  // Initialize config draft from connector config
  useEffect(() => {
    const draft: Record<string, string> = {};
    for (const field of fields) {
      const val = connector.config[field.key];
      if (Array.isArray(val)) {
        draft[field.key] = val.join('\n');
      } else if (val !== undefined && val !== null) {
        draft[field.key] = String(val);
      } else {
        draft[field.key] = '';
      }
    }
    setConfigDraft(draft);
  }, [connector.config, connector.name]);

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await onSync(connector.name);
      setSyncResult(result);
    } finally {
      setSyncing(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Convert draft values back to proper types
      const config: Record<string, unknown> = {};
      for (const field of fields) {
        const val = configDraft[field.key] || '';
        if (field.type === 'textarea') {
          // Split by newlines for array fields
          config[field.key] = val.split('\n').map(s => s.trim()).filter(Boolean);
        } else if (field.key === 'include_bots') {
          config[field.key] = val.toLowerCase() === 'true';
        } else if (field.key === 'max_file_size_mb') {
          const n = parseInt(val);
          if (!isNaN(n)) config[field.key] = n;
        } else if (field.key === 'extensions') {
          config[field.key] = val.split(',').map(s => s.trim()).filter(Boolean);
        } else if (val) {
          config[field.key] = val;
        }
      }
      await onSave(connector.name, config);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors"
      >
        <span className="text-2xl flex-shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">{connector.name}</h3>
            <span className="text-[10px] font-mono text-gray-400">v{connector.version}</span>
            {connector.configured && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 font-medium">
                Configured
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{connector.description}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleSync();
            }}
            disabled={syncing}
            className="tap-sm flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-accent-blue/10 text-accent-blue hover:bg-accent-blue/20 disabled:opacity-50 transition-colors font-medium"
          >
            {syncing ? (
              <><svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Syncing…</>
            ) : (
              <><svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> Sync</>
            )}
          </button>
          <svg className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </button>

      {/* Sync result */}
      {syncResult && (
        <div className={`mx-4 mb-3 text-xs px-3 py-2 rounded-lg ${
          syncResult.errors > 0
            ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800/40'
            : 'bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800/40'
        }`}>
          {syncResult.documents_found === 0
            ? 'No documents found. Check the connector configuration.'
            : `Found ${syncResult.documents_found} documents, indexed ${syncResult.documents_indexed}${syncResult.errors > 0 ? `, ${syncResult.errors} errors` : ''}`
          }
        </div>
      )}

      {/* Configuration panel */}
      {expanded && fields.length > 0 && (
        <div className="px-4 pb-4 pt-1 border-t border-gray-100 dark:border-dark-border space-y-3 animate-slideDown">
          {fields.map((field) => (
            <div key={field.key}>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{field.label}</label>
              {field.type === 'textarea' ? (
                <textarea
                  value={configDraft[field.key] || ''}
                  onChange={(e) => setConfigDraft({ ...configDraft, [field.key]: e.target.value })}
                  rows={3}
                  placeholder={field.placeholder}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono resize-none"
                />
              ) : (
                <input
                  type="text"
                  value={configDraft[field.key] || ''}
                  onChange={(e) => setConfigDraft({ ...configDraft, [field.key]: e.target.value })}
                  placeholder={field.placeholder}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono"
                />
              )}
              {field.help && <p className="text-[11px] text-gray-400 mt-1">{field.help}</p>}
            </div>
          ))}

          <button
            onClick={handleSave}
            disabled={saving}
            className="tap-sm flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-50 transition-colors font-medium"
          >
            {saving ? 'Saving…' : '💾 Save Configuration'}
          </button>
        </div>
      )}

      {expanded && fields.length === 0 && (
        <div className="px-4 pb-4 pt-1 border-t border-gray-100 dark:border-dark-border">
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">
            This connector works automatically with no configuration needed.
          </p>
        </div>
      )}
    </div>
  );
}

export default function DataSources() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/connectors`);
        if (res.ok && active) {
          const data = await res.json();
          setConnectors(data.connectors || []);
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

  const handleSync = async (name: string): Promise<ConnectorSyncResult | null> => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/connectors/${name}/sync`, { method: 'POST' });
      if (res.ok) {
        return await res.json();
      }
      return null;
    } catch {
      return null;
    }
  };

  const handleSave = async (name: string, config: Record<string, unknown>): Promise<boolean> => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/connectors/${name}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config }),
      });
      if (res.ok) {
        // Refresh connectors list
        const listRes = await fetch(`${API_BASE_URL}/api/connectors`);
        if (listRes.ok) {
          const data = await listRes.json();
          setConnectors(data.connectors || []);
        }
        return true;
      }
      return false;
    } catch {
      return false;
    }
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-6 space-y-4">
        <div className="h-7 bg-gray-200 dark:bg-dark-border rounded-lg w-40 animate-pulse" />
        {[1, 2, 3].map(i => (
          <div key={i} className="h-20 bg-gray-200 dark:bg-dark-border rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-5 pb-10">
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">Data Sources</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Connect external data sources to make them searchable alongside your local files.
        </p>
      </div>

      {/* Info banner */}
      <div className="text-sm px-4 py-3 rounded-xl bg-accent-blue/5 dark:bg-accent-blue/10 border border-accent-blue/20 text-gray-600 dark:text-gray-300 flex items-start gap-2">
        <span>💡</span>
        <span>
          Configure a data source, then click <strong>Sync</strong> to import its content into your search index.
          You can sync at any time to pull in new data.
        </span>
      </div>

      {/* Connector cards */}
      <div className="space-y-3">
        {connectors.map(conn => (
          <ConnectorCard
            key={conn.name}
            connector={conn}
            onSync={handleSync}
            onSave={handleSave}
          />
        ))}
      </div>

      {connectors.length === 0 && (
        <div className="text-center py-12">
          <p className="text-gray-400 dark:text-gray-500">No connectors available.</p>
        </div>
      )}
    </div>
  );
}
