import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import type { FolderInfo } from '../types';

function timeAgo(dateStr: string): string {
  const d = new Date(dateStr);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? '' : 's'} ago`;
  return `${Math.floor(hrs / 24)} day${Math.floor(hrs / 24) === 1 ? '' : 's'} ago`;
}

// ── Folder browser modal ─────────────────────────────────────────────────────
interface DirEntry { name: string; path: string; }
interface BrowseResult { current: string; parent: string | null; directories: DirEntry[]; }

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
    <div className="fixed inset-0 bg-black/50 flex items-end sm:items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-dark-border flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">Choose a Folder</h3>
            <p className="text-xs text-gray-400 mt-0.5 font-mono truncate max-w-[280px]">{browsePath}</p>
          </div>
          <button
            onClick={onClose}
            className="tap-sm p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="max-h-72 sm:max-h-80 overflow-y-auto">
          {browseResult?.parent && (
            <button
              onClick={() => loadDir(browseResult.parent!)}
              className="tap-sm w-full text-left px-5 py-3 text-sm hover:bg-gray-50 dark:hover:bg-dark-hover flex items-center gap-3 text-gray-600 dark:text-gray-300 border-b border-gray-100 dark:border-dark-border"
            >
              <span className="text-lg">📁</span>
              <span className="font-mono text-xs">..</span>
              <span className="text-gray-400">Go up</span>
            </button>
          )}
          {browseLoading ? (
            <div className="px-5 py-10 text-center text-gray-400 text-sm">Loading…</div>
          ) : browseResult?.directories.length === 0 ? (
            <div className="px-5 py-10 text-center text-gray-400 text-sm">No subfolders here</div>
          ) : (
            browseResult?.directories.map((dir) => (
              <button
                key={dir.path}
                onClick={() => loadDir(dir.path)}
                className="tap-sm w-full text-left px-5 py-3 text-sm hover:bg-gray-50 dark:hover:bg-dark-hover flex items-center gap-3 text-gray-700 dark:text-gray-200"
              >
                <span className="text-lg">📂</span>
                <span className="truncate">{dir.name}</span>
              </button>
            ))
          )}
        </div>

        <div className="px-5 py-4 border-t border-gray-200 dark:border-dark-border flex justify-between items-center gap-3 bg-gray-50 dark:bg-dark-hover/50">
          <p className="text-xs text-gray-400 truncate flex-1">{browsePath}</p>
          <div className="flex gap-2 flex-shrink-0">
            <button
              onClick={onClose}
              className="tap-sm px-4 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => { onSelect(browsePath); onClose(); }}
              className="tap-sm px-5 py-2 text-sm rounded-xl bg-accent-blue text-white hover:bg-accent-blue-hover transition-colors font-medium"
            >
              Add This Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Indexing progress bar ─────────────────────────────────────────────────────
interface IndexProgress {
  status: string;
  file: string | null;
  message: string;
  current: number;
  total: number;
}

function FolderIndexingBar({ progress }: { progress: IndexProgress }) {
  const filename = progress.file ? progress.file.split('/').pop() : null;
  const pct = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : null;

  let description = 'Getting started…';
  if (progress.status === 'discovery') description = 'Finding files to index…';
  else if (progress.status === 'parsing' || progress.status === 'reading') description = filename ? `Reading "${filename}"` : 'Reading files…';
  else if (progress.status === 'embedding') description = filename ? `Understanding "${filename}"` : 'Processing files…';
  else if (progress.status === 'storing') description = 'Saving index…';
  else if (filename) description = `Processing "${filename}"`;

  return (
    <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40 rounded-xl p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0" />
          <span className="text-sm font-medium text-amber-800 dark:text-amber-300 truncate">
            {description}
          </span>
        </div>
        {pct !== null && (
          <span className="text-xs text-amber-600 dark:text-amber-400 flex-shrink-0 ml-2 tabular-nums">
            {progress.current} / {progress.total}
          </span>
        )}
      </div>
      <div className="w-full bg-amber-200 dark:bg-amber-800/50 rounded-full h-1.5 overflow-hidden">
        <div
          className="h-full bg-amber-500 dark:bg-amber-400 rounded-full transition-all duration-300 ease-out"
          style={{ width: pct !== null ? `${pct}%` : '100%' }}
        />
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function FolderManager() {
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [newPath, setNewPath] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showBrowser, setShowBrowser] = useState(false);
  const [indexProgress, setIndexProgress] = useState<IndexProgress | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

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
          loadFolders();
        } else {
          if (data.current === 0 && data.total === 0 && data.status === 'discovery') {
            setIndexProgress(prev => prev ? { ...prev, message: data.message || 'Scanning…' } : data);
          } else {
            setIndexProgress(data);
          }
        }
      };
      ws.onclose = () => { reconnectTimer = setTimeout(connect, 3000); };
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
        setError(data.detail || 'Couldn\'t add that folder — make sure the path exists.');
        return;
      }
      setNewPath('');
      await loadFolders();
    } catch {
      setError('Couldn\'t connect to DeskSearch. Is the app running?');
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

  const clearFolderIndex = async (path: string) => {
    if (!confirm(`This will remove the search index for:\n\n${path}\n\nThe folder stays in your list and can be re-indexed anytime.`)) return;
    setActionLoading(`clear-${path}`);
    try {
      await fetch(`${API_BASE_URL}/api/index/folder/${encodeURIComponent(path)}`, { method: 'DELETE' });
      await loadFolders();
    } catch {
      // ignore
    } finally {
      setActionLoading(null);
    }
  };

  const clearAllIndex = async () => {
    if (!confirm('This will clear the entire search index and you\'ll need to re-index your folders.\n\nYour folder list will stay. Continue?')) return;
    setActionLoading('clear-all');
    try {
      await fetch(`${API_BASE_URL}/api/index/clear`, { method: 'DELETE' });
      await loadFolders();
    } catch {
      // ignore
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
        <div className="h-6 bg-gray-200 dark:bg-dark-border rounded w-48 animate-pulse" />
        <div className="h-12 bg-gray-200 dark:bg-dark-border rounded-xl animate-pulse" />
        {[1, 2].map(i => (
          <div key={i} className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl p-4 animate-pulse">
            <div className="h-4 bg-gray-200 dark:bg-dark-border rounded w-3/4 mb-2" />
            <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">Your Search Folders</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          DeskSearch will index files in these folders so you can search them.
        </p>
      </div>

      {/* Add folder */}
      <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Add a folder</h3>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addFolder()}
            placeholder="Type a folder path, or click Browse…"
            className="flex-1 px-3 py-2.5 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-blue/50 focus:border-accent-blue"
          />
          <div className="flex gap-2">
            <button
              onClick={() => setShowBrowser(true)}
              className="tap-sm flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-4 py-2.5 text-sm rounded-xl border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors font-medium"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              Browse
            </button>
            <button
              onClick={() => addFolder()}
              disabled={actionLoading === 'add' || !newPath.trim()}
              className="tap-sm flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-5 py-2.5 text-sm rounded-xl bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {actionLoading === 'add' ? (
                <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Adding…</>
              ) : (
                <><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"/></svg> Add Folder</>
              )}
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 px-3 py-2 rounded-lg">
            <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
            </svg>
            {error}
          </div>
        )}
      </div>

      {/* Indexing progress */}
      {indexProgress && <FolderIndexingBar progress={indexProgress} />}

      {/* Folder browser modal */}
      {showBrowser && (
        <FolderBrowser
          onSelect={(path) => addFolder(path)}
          onClose={() => setShowBrowser(false)}
        />
      )}

      {/* Folder list */}
      {folders.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-14 text-center animate-fadeIn">
          <div className="w-20 h-20 rounded-2xl bg-accent-blue/10 flex items-center justify-center mb-5">
            <svg className="w-10 h-10 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-2">No folders added yet</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
            Click <strong>Browse</strong> to pick a folder from your computer,
            or type a path above and click <strong>Add Folder</strong>.
          </p>
          <p className="text-sm text-gray-400 dark:text-gray-500 mt-3">
            Good places to start: Documents, Desktop, Downloads
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {folders.map((folder) => (
            <FolderCard
              key={folder.path}
              folder={folder}
              actionLoading={actionLoading}
              onReindex={reindexFolder}
              onRemove={removeFolder}
              onClearIndex={clearFolderIndex}
              showAdvanced={showAdvanced}
            />
          ))}

          {/* Advanced section */}
          <div className="pt-2">
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="tap-sm flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <svg className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              {showAdvanced ? 'Hide advanced options' : 'Show advanced options'}
            </button>

            {showAdvanced && (
              <div className="mt-3 p-4 bg-gray-50 dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl space-y-2 animate-slideDown">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  These options are rarely needed. Use them only if your search results seem outdated or wrong.
                </p>
                <button
                  onClick={clearAllIndex}
                  disabled={actionLoading === 'clear-all'}
                  className="tap-sm w-full text-left px-4 py-3 text-sm rounded-lg border border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-50 transition-colors"
                >
                  {actionLoading === 'clear-all' ? 'Clearing…' : '🗑️  Clear all search data and start over'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Folder card component ─────────────────────────────────────────────────────
function FolderCard({
  folder,
  actionLoading,
  onReindex,
  onRemove,
  onClearIndex,
  showAdvanced,
}: {
  folder: FolderInfo;
  actionLoading: string | null;
  onReindex: (path: string) => void;
  onRemove: (path: string) => void;
  onClearIndex: (path: string) => void;
  showAdvanced: boolean;
}) {
  const isWatching = folder.status === 'watching';
  const displayPath = folder.path.replace(/^\/Users\/[^/]+/, '~');

  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl p-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        {/* Folder info */}
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${
            isWatching ? 'bg-green-100 dark:bg-green-950/40' : 'bg-gray-100 dark:bg-dark-hover'
          }`}>
            <svg className={`w-5 h-5 ${isWatching ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 dark:text-white truncate" title={folder.path}>
              {displayPath}
            </p>
            <div className="flex flex-wrap items-center gap-2 mt-1 text-xs">
              {/* File count */}
              <span className="text-gray-500 dark:text-gray-400">
                {folder.file_count > 0
                  ? `${folder.file_count.toLocaleString()} file${folder.file_count === 1 ? '' : 's'} searchable`
                  : 'No files indexed yet'}
              </span>
              {/* Last indexed */}
              {folder.last_indexed && (
                <span className="text-gray-400 dark:text-gray-500">
                  · Updated {timeAgo(folder.last_indexed)}
                </span>
              )}
              {/* Status badge */}
              <span className={`tap-sm inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium ${
                isWatching
                  ? 'bg-green-100 dark:bg-green-950/40 text-green-700 dark:text-green-400'
                  : 'bg-gray-100 dark:bg-dark-hover text-gray-500 dark:text-gray-400'
              }`}>
                <span className={`w-1 h-1 rounded-full ${isWatching ? 'bg-green-500' : 'bg-gray-400'}`} />
                {isWatching ? 'Watching for changes' : folder.status}
              </span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2 pl-12 sm:pl-0">
          <button
            onClick={() => onReindex(folder.path)}
            disabled={actionLoading === `reindex-${folder.path}`}
            className="tap-sm flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-2 text-xs rounded-lg border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover disabled:opacity-50 transition-colors font-medium"
            title="Re-scan this folder to pick up new and changed files"
          >
            {actionLoading === `reindex-${folder.path}` ? (
              <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            ) : (
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            )}
            {actionLoading === `reindex-${folder.path}` ? 'Refreshing…' : 'Refresh files'}
          </button>

          {showAdvanced && (
            <button
              onClick={() => onClearIndex(folder.path)}
              disabled={actionLoading === `clear-${folder.path}`}
              className="tap-sm flex-1 sm:flex-none px-3 py-2 text-xs rounded-lg border border-amber-200 dark:border-amber-900/50 text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-50 transition-colors font-medium"
              title="Remove the index for this folder only"
            >
              {actionLoading === `clear-${folder.path}` ? 'Clearing…' : 'Clear index'}
            </button>
          )}

          <button
            onClick={() => onRemove(folder.path)}
            disabled={!!actionLoading && actionLoading !== folder.path}
            className="tap-sm flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-2 text-xs rounded-lg border border-red-200 dark:border-red-900/50 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-50 transition-colors font-medium"
            title="Remove this folder from DeskSearch"
          >
            {actionLoading === folder.path ? (
              <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            ) : (
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
            )}
            {actionLoading === folder.path ? 'Removing…' : 'Remove'}
          </button>
        </div>
      </div>
    </div>
  );
}
