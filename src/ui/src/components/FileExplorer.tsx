import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import type { FileInfo, FilesResponse } from '../types';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

type SortField = 'filename' | 'path' | 'type' | 'size' | 'modified' | 'num_chunks' | 'indexed_time';

export default function FileExplorer() {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [sortBy, setSortBy] = useState<SortField>('indexed_time');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<{ filename: string; content: string } | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const loadFiles = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      if (search) params.set('search', search);
      if (typeFilter) params.set('file_type', typeFilter);

      const res = await fetch(`${API_BASE_URL}/api/files?${params}`);
      if (res.ok) {
        const data: FilesResponse = await res.json();
        setFiles(data.files);
        setTotal(data.total);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, sortBy, sortDir, search, typeFilter]);

  useEffect(() => { loadFiles(); }, [loadFiles]);

  // Debounce search
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortDir('asc');
    }
    setPage(1);
  };

  const loadPreview = async (docId: number, filename: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/files/${docId}/preview`);
      if (res.ok) {
        const data = await res.json();
        setPreview({ filename, content: data.content });
      }
    } catch {
      // ignore
    }
  };

  const toggleSelect = (docId: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const removeSelected = async () => {
    for (const docId of selected) {
      await fetch(`${API_BASE_URL}/api/files/${docId}`, { method: 'DELETE' });
    }
    setSelected(new Set());
    loadFiles();
  };

  const totalPages = Math.ceil(total / pageSize);

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortBy !== field) return null;
    return <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>;
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setPreview(null)}>
          <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg max-w-3xl w-full max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-dark-border">
              <span className="font-medium text-sm text-gray-900 dark:text-white">{preview.filename}</span>
              <button onClick={() => setPreview(null)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-4 text-xs text-gray-700 dark:text-gray-300 font-mono whitespace-pre-wrap">
              {preview.content}
            </pre>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Indexed Files</h2>
        <div className="text-sm text-gray-500">{total.toLocaleString()} files</div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search files..."
          className="flex-1 max-w-xs px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-blue/50"
        />
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
          className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface text-gray-900 dark:text-white focus:outline-none"
        >
          <option value="">All types</option>
          {['pdf', 'txt', 'md', 'py', 'js', 'ts', 'json', 'html', 'docx', 'csv'].map(t => (
            <option key={t} value={t}>.{t}</option>
          ))}
        </select>
        {selected.size > 0 && (
          <button
            onClick={removeSelected}
            className="px-3 py-1.5 text-xs rounded-lg border border-red-200 dark:border-red-900/50 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          >
            Remove {selected.size} selected
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-gray-200 dark:border-dark-border rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 dark:bg-dark-hover text-left text-xs text-gray-500 dark:text-gray-400">
              <th className="px-3 py-2 w-8">
                <input
                  type="checkbox"
                  checked={selected.size === files.length && files.length > 0}
                  onChange={() => {
                    if (selected.size === files.length) setSelected(new Set());
                    else setSelected(new Set(files.map(f => f.doc_id)));
                  }}
                  className="rounded"
                />
              </th>
              <ThSortable field="filename" current={sortBy} onClick={handleSort}>Name<SortIcon field="filename" /></ThSortable>
              <ThSortable field="type" current={sortBy} onClick={handleSort}>Type<SortIcon field="type" /></ThSortable>
              <ThSortable field="size" current={sortBy} onClick={handleSort}>Size<SortIcon field="size" /></ThSortable>
              <ThSortable field="modified" current={sortBy} onClick={handleSort}>Modified<SortIcon field="modified" /></ThSortable>
              <ThSortable field="num_chunks" current={sortBy} onClick={handleSort}>Chunks<SortIcon field="num_chunks" /></ThSortable>
              <ThSortable field="indexed_time" current={sortBy} onClick={handleSort}>Indexed<SortIcon field="indexed_time" /></ThSortable>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-400">Loading...</td></tr>
            ) : files.length === 0 ? (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-400">No files found</td></tr>
            ) : (
              files.map((f) => (
                <tr
                  key={f.doc_id}
                  className="border-t border-gray-100 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors"
                >
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(f.doc_id)}
                      onChange={() => toggleSelect(f.doc_id)}
                      className="rounded"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => loadPreview(f.doc_id, f.filename)}
                      className="text-accent-blue hover:underline truncate max-w-[200px] block text-left"
                      title={f.path}
                    >
                      {f.filename}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-gray-500">
                    <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-dark-hover text-xs font-mono">
                      .{f.file_type}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-500 tabular-nums">{formatSize(f.size)}</td>
                  <td className="px-3 py-2 text-gray-500">{formatDate(f.modified)}</td>
                  <td className="px-3 py-2 text-gray-500 tabular-nums">{f.num_chunks}</td>
                  <td className="px-3 py-2 text-gray-500">{formatDate(f.indexed_time)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <div className="text-gray-500">
            Page {page} of {totalPages}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-3 py-1 rounded border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover disabled:opacity-50 transition-colors"
            >
              Prev
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1 rounded border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover disabled:opacity-50 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ThSortable({ field, current, onClick, children }: {
  field: SortField;
  current: SortField;
  onClick: (f: SortField) => void;
  children: React.ReactNode;
}) {
  return (
    <th
      className={`px-3 py-2 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none ${
        current === field ? 'text-gray-700 dark:text-gray-200' : ''
      }`}
      onClick={() => onClick(field)}
    >
      {children}
    </th>
  );
}
