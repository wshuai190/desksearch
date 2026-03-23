import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../config';
import type { RichPreview } from '../types';

// Reuse the file icon map inline
const FILE_ICONS: Record<string, { icon: string; bg: string; fg: string }> = {
  pdf:   { icon: '📄', bg: 'bg-red-50 dark:bg-red-900/20',   fg: 'text-red-500' },
  docx:  { icon: '📝', bg: 'bg-blue-50 dark:bg-blue-900/20', fg: 'text-blue-600' },
  doc:   { icon: '📝', bg: 'bg-blue-50 dark:bg-blue-900/20', fg: 'text-blue-600' },
  md:    { icon: '📝', bg: 'bg-gray-50 dark:bg-gray-800',     fg: 'text-gray-600' },
  txt:   { icon: '📃', bg: 'bg-gray-50 dark:bg-gray-800',     fg: 'text-gray-500' },
  py:    { icon: '🐍', bg: 'bg-yellow-50 dark:bg-yellow-900/20', fg: 'text-yellow-600' },
  js:    { icon: '⚡', bg: 'bg-yellow-50 dark:bg-yellow-900/20', fg: 'text-yellow-500' },
  ts:    { icon: '⚡', bg: 'bg-blue-50 dark:bg-blue-900/20',  fg: 'text-blue-500' },
  json:  { icon: '📋', bg: 'bg-orange-50 dark:bg-orange-900/20', fg: 'text-orange-500' },
  csv:   { icon: '📊', bg: 'bg-green-50 dark:bg-green-900/20', fg: 'text-green-600' },
  ipynb: { icon: '📓', bg: 'bg-orange-50 dark:bg-orange-900/20', fg: 'text-orange-500' },
};

function getFileIcon(type: string) {
  return FILE_ICONS[type.toLowerCase()] ?? { icon: '📄', bg: 'bg-gray-50 dark:bg-gray-800', fg: 'text-gray-500' };
}

function formatBytes(bytes?: number): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatDate(iso?: string): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'long', day: 'numeric', year: 'numeric',
  });
}

interface DocumentPreviewPanelProps {
  docId: number | null;
  filename: string;
  path: string;
  fileType: string;
  onClose: () => void;
}

export default function DocumentPreviewPanel({
  docId,
  filename,
  path,
  fileType,
  onClose,
}: DocumentPreviewPanelProps) {
  const [preview, setPreview] = useState<RichPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (docId === null) return;
    setLoading(true);
    setError(null);
    setPreview(null);

    fetch(`${API_BASE_URL}/api/preview/${docId}`)
      .then(r => {
        if (!r.ok) throw new Error('Preview unavailable');
        return r.json();
      })
      .then(data => setPreview(data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [docId]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const { icon, bg, fg } = getFileIcon(fileType);
  const shortPath = path.replace(/^\/Users\/[^/]+/, '~');

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 dark:bg-black/40 backdrop-blur-sm z-40 animate-fadeIn"
        onClick={onClose}
      />

      {/* Slide-out panel */}
      <div
        ref={panelRef}
        className="fixed top-0 right-0 h-full w-full max-w-md bg-white dark:bg-dark-surface shadow-2xl z-50 flex flex-col animate-slideInRight"
        style={{ animationDuration: '220ms' }}
      >
        {/* Header */}
        <div className="flex items-start gap-3 px-5 pt-5 pb-4 border-b border-gray-100 dark:border-dark-border">
          {/* File icon badge */}
          <div className={`flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-xl ${bg}`}>
            <span className={fg}>{icon}</span>
          </div>

          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100 truncate leading-snug" title={filename}>
              {filename}
            </h2>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate" title={path}>
              {shortPath}
            </p>
          </div>

          <button
            onClick={onClose}
            className="flex-shrink-0 p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
            title="Close (Esc)"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="p-5 space-y-3 animate-pulse">
              <div className="flex gap-4">
                {[1,2,3].map(i => (
                  <div key={i} className="flex-1 h-12 bg-gray-100 dark:bg-dark-border rounded-lg" />
                ))}
              </div>
              <div className="h-4 bg-gray-100 dark:bg-dark-border rounded w-1/3 mt-4" />
              <div className="space-y-2">
                {[1,2,3,4,5].map(i => (
                  <div key={i} className={`h-3 bg-gray-100 dark:bg-dark-border rounded ${i === 3 ? 'w-3/4' : 'w-full'}`} />
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="p-5">
              <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 p-4 text-sm text-red-600 dark:text-red-400">
                {error}
              </div>
            </div>
          )}

          {preview && !loading && (
            <>
              {/* Stats bar */}
              <div className="grid grid-cols-3 gap-px bg-gray-100 dark:bg-dark-border border-b border-gray-100 dark:border-dark-border">
                {[
                  { label: 'Size', value: formatBytes(preview.size) || '—' },
                  { label: 'Words', value: preview.word_count > 0 ? preview.word_count.toLocaleString() : '—' },
                  { label: 'Chunks', value: preview.num_chunks.toString() },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-white dark:bg-dark-surface px-4 py-3 text-center">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{value}</div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-0.5">{label}</div>
                  </div>
                ))}
              </div>

              {/* Modified date */}
              {preview.modified && (
                <div className="px-5 pt-4 flex items-center gap-1.5 text-xs text-gray-400">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  Last modified: <span className="text-gray-500">{formatDate(preview.modified)}</span>
                </div>
              )}

              {/* Key phrases */}
              {preview.key_phrases.length > 0 && (
                <div className="px-5 pt-4">
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2.5">
                    Key Topics
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {preview.key_phrases.map((phrase) => (
                      <span
                        key={phrase}
                        className="text-xs px-2.5 py-1 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-100 dark:border-blue-900/50 rounded-full font-medium"
                      >
                        {phrase}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Preview text */}
              <div className="px-5 pt-4 pb-2">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2.5">
                  Content Preview
                </h3>
                <div className="rounded-lg bg-gray-50 dark:bg-dark-hover border border-gray-100 dark:border-dark-border p-4">
                  <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap font-mono text-[13px]">
                    {preview.preview_text}
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer actions */}
        <div className="px-5 py-4 border-t border-gray-100 dark:border-dark-border flex gap-2">
          <button
            onClick={() => fetch(`${API_BASE_URL}/api/open/${encodeURIComponent(path)}`)}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-accent-blue text-white text-sm font-medium rounded-lg hover:bg-blue-600 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            Open File
          </button>
          <button
            onClick={async () => { await navigator.clipboard.writeText(path); }}
            className="px-4 py-2.5 border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors"
            title="Copy path"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </div>
    </>
  );
}
