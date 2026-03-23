import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import type { FolderInfo } from '../types';

function timeAgo(dateStr: string): string {
  const d = new Date(dateStr);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface DirEntry {
  name: string;
  path: string;
}

interface BrowseResult {
  current: string;
  parent: string | null;
  directories: DirEntry[];
}

function FolderBrowser({ onSelect, onClose }: { onSelect: (path: string) => void; onClose: () => void }) {
  const [browsePath, setBrowsePath] = useState('~');
  const [browseResult, setBrowseResult] = useState<BrowseResult | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);

  const loadDir = useCallback(async (dirPath: string) => {
    setBrowseLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/browse-directories?path=${encodeURIComponent(dirPath)}`);
      if (res.ok) {
        const data = await res.json();
        setBrowseResult(data);
        setBrowsePath(data.current);
      }
    } catch {
      // ignore
    } finally {
      setBrowseLoading(false);
    }
  }, []);

  useEffect(() => { loadDir('~'); }, [loadDir]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Choose a Folder</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-lg">✕</button>
        </div>

        {/* Current path */}
        <div className="px-4 py-2 bg-gray-50 dark:bg-dark-bg text-xs text-gray-500 dark:text-gray-400 font-mono truncate">
          {browsePath}
        </div>

        {/* Directory list */}
        <div className="max-h-80 overflow-y-auto">
          {browseResult?.parent && (
            <button
              onClick={() => loadDir(browseResult.parent!)}
              className="w-full text-left px-4 py-2.5 text-sm hover:bg-gray-100 dark:hover:bg-dark-hover flex items-center gap-2 text-gray-600 dark:text-gray-300 border-b border-gray-100 dark:border-dark-border"
            >
              <span className="text-base">📁</span>
              <span>..</span>
            </button>
          )}
          {browseLoading ? (
            <div className="px-4 py-8 text-center text-gray-400 text-sm">Loading...</div>
          ) : browseResult?.directories.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-400 text-sm">No subdirectories</div>
          ) : (
            browseResult?.directories.map((dir) => (
              <button
                key={dir.path}
                onClick={() => loadDir(dir.path)}
                className="w-full text-left px-4 py-2.5 text-sm hover:bg-gray-100 dark:hover:bg-dark-hover flex items-center gap-2 text-gray-700 dark:text-gray-200"
              >
                <span className="text-base">📂</span>
                <span className="truncate">{dir.name}</span>
              </button>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-200 dark:border-dark-border flex justify-between items-center">
          <span className="text-xs text-gray-400 truncate max-w-[60%]">{browsePath}</span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => { onSelect(browsePath); onClose(); }}
              className="px-4 py-1.5 text-sm rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover transition-colors"
            >
              Select This Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface IndexProgress {
  status: string;
  file: string | null;
  message: string;
  current: number;
  total: number;
}

export default function FolderManager() {
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [newPath, setNewPath] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showBrowser, setShowBrowser] = useState(false);
  const [indexProgress, setIndexProgress] = useState<IndexProgress | null>(null);

  const loadFolders = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/folders`);
      if (res.ok) setFolders(await res.json());
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadFolders(); }, [loadFolders]);

  // WebSocket for indexing progress
  useEffect(() => {
    const wsUrl = API_BASE_URL.replace(/^http/, 'ws') + '/ws/index-progress';
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data) as IndexProgress;
        if (data.status === 'complete') {
          setIndexProgress(null);
          loadFolders(); // refresh counts
        } else {
          // Don't reset progress bar if we get 0/0 during discovery phase
          if (data.current === 0 && data.total === 0 && data.status === 'discovery') {
            setIndexProgress(prev => prev ? { ...prev, message: data.message || 'Scanning...' } : data);
          } else {
            setIndexProgress(data);
          }
        }
      };
      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 3000);
      };
    }
    connect();

    return () => {
      if (ws) ws.close();
      clearTimeout(reconnectTimer);
    };
  }, [loadFolders]);

  const addFolder = async (folderPath?: string) => {
    const pathToAdd = folderPath || newPath.trim();
    if (!pathToAdd) return;
    setError('');
    setActionLoading('add');
    try {
      const res = await fetch(`${API_BASE_URL}/api/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathToAdd }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || 'Failed to add folder');
        return;
      }
      setNewPath('');
      await loadFolders();
    } catch {
      setError('Network error');
    } finally {
      setActionLoading(null);
    }
  };

  const removeFolder = async (path: string) => {
    setActionLoading(path);
    try {
      await fetch(`${API_BASE_URL}/api/folders/${encodeURIComponent(path)}`, { method: 'DELETE' });
      await loadFolders();
    } catch {
      // ignore
    } finally {
      setActionLoading(null);
    }
  };

  const reindexFolder = async (path: string) => {
    setActionLoading(`reindex-${path}`);
    try {
      await fetch(`${API_BASE_URL}/api/reindex/${encodeURIComponent(path)}`, { method: 'POST' });
    } catch {
      // ignore
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-400">Loading folders...</div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Watched Folders</h2>

      {/* Add folder */}
      <div className="flex gap-2">
        <input
          type="text"
          value={newPath}
          onChange={(e) => setNewPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addFolder()}
          placeholder="Enter folder path or use Browse..."
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-blue/50"
        />
        <button
          onClick={() => setShowBrowser(true)}
          className="px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
          title="Browse folders"
        >
          📁 Browse
        </button>
        <button
          onClick={() => addFolder()}
          disabled={actionLoading === 'add' || !newPath.trim()}
          className="px-4 py-2 text-sm rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-50 transition-colors"
        >
          {actionLoading === 'add' ? 'Adding...' : 'Add'}
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-500 bg-red-500/10 px-3 py-2 rounded-lg">{error}</div>
      )}

      {/* Indexing progress */}
      {indexProgress && (
        <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
              <span className="inline-block w-2 h-2 bg-accent-blue rounded-full animate-pulse" />
              Indexing...
            </span>
            <span className="text-xs text-gray-500">
              {indexProgress.current} / {indexProgress.total}
            </span>
          </div>
          {/* Progress bar */}
          <div className="w-full bg-gray-200 dark:bg-dark-border rounded-full h-2 overflow-hidden">
            <div
              className="bg-accent-blue h-2 rounded-full transition-all duration-300 ease-out"
              style={{ width: indexProgress.total > 0 ? `${(indexProgress.current / indexProgress.total) * 100}%` : '0%' }}
            />
          </div>
          {/* Current file */}
          {indexProgress.file && (
            <div className="text-xs text-gray-400 truncate" title={indexProgress.file}>
              {indexProgress.status === 'parsing' ? '📄' : indexProgress.status === 'embedding' ? '🧠' : '💾'}{' '}
              {indexProgress.file.split('/').pop()}
              {indexProgress.message && ` — ${indexProgress.message}`}
            </div>
          )}
        </div>
      )}

      {/* Folder browser modal */}
      {showBrowser && (
        <FolderBrowser
          onSelect={(path) => addFolder(path)}
          onClose={() => setShowBrowser(false)}
        />
      )}

      {/* Folder list */}
      {folders.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No watched folders. Add a folder path above or use Browse to start indexing.
        </div>
      ) : (
        <div className="space-y-2">
          {folders.map((folder) => (
            <div
              key={folder.path}
              className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 dark:text-white truncate" title={folder.path}>
                    {folder.path}
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
                    <span>{folder.file_count} files indexed</span>
                    {folder.last_indexed && <span>Last indexed: {timeAgo(folder.last_indexed)}</span>}
                    <span className={`px-1.5 py-0.5 rounded ${
                      folder.status === 'watching'
                        ? 'bg-green-500/10 text-green-500'
                        : 'bg-gray-500/10 text-gray-500'
                    }`}>
                      {folder.status}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => reindexFolder(folder.path)}
                    disabled={actionLoading === `reindex-${folder.path}`}
                    className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover disabled:opacity-50 transition-colors"
                    title="Reindex folder"
                  >
                    {actionLoading === `reindex-${folder.path}` ? 'Reindexing...' : 'Reindex'}
                  </button>
                  <button
                    onClick={() => removeFolder(folder.path)}
                    disabled={actionLoading === folder.path}
                    className="px-3 py-1.5 text-xs rounded-lg border border-red-200 dark:border-red-900/50 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
                    title="Remove folder"
                  >
                    {actionLoading === folder.path ? 'Removing...' : 'Remove'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
