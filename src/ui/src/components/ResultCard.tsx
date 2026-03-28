import { useState } from 'react';
import type { RichSearchResult, RelatedDoc } from '../types';
import { API_BASE_URL } from '../config';
import DocumentPreviewPanel from './DocumentPreviewPanel';

// ── File type icon with colored badge ───────────────────────────────────────
const FILE_TYPE_STYLES: Record<string, { bg: string; ring: string; text: string }> = {
  pdf:   { bg: 'bg-red-500',    ring: 'ring-red-500/20',    text: 'PDF' },
  txt:   { bg: 'bg-gray-500',   ring: 'ring-gray-500/20',   text: 'TXT' },
  md:    { bg: 'bg-gray-600',   ring: 'ring-gray-600/20',   text: 'MD' },
  doc:   { bg: 'bg-blue-600',   ring: 'ring-blue-600/20',   text: 'DOC' },
  docx:  { bg: 'bg-blue-600',   ring: 'ring-blue-600/20',   text: 'DOC' },
  xls:   { bg: 'bg-emerald-600', ring: 'ring-emerald-600/20', text: 'XLS' },
  xlsx:  { bg: 'bg-emerald-600', ring: 'ring-emerald-600/20', text: 'XLS' },
  csv:   { bg: 'bg-emerald-500', ring: 'ring-emerald-500/20', text: 'CSV' },
  py:    { bg: 'bg-sky-600',    ring: 'ring-sky-600/20',    text: 'PY' },
  js:    { bg: 'bg-yellow-500', ring: 'ring-yellow-500/20', text: 'JS' },
  ts:    { bg: 'bg-blue-500',   ring: 'ring-blue-500/20',   text: 'TS' },
  tsx:   { bg: 'bg-blue-400',   ring: 'ring-blue-400/20',   text: 'TSX' },
  jsx:   { bg: 'bg-blue-400',   ring: 'ring-blue-400/20',   text: 'JSX' },
  rs:    { bg: 'bg-orange-600', ring: 'ring-orange-600/20', text: 'RS' },
  go:    { bg: 'bg-cyan-600',   ring: 'ring-cyan-600/20',   text: 'GO' },
  java:  { bg: 'bg-orange-700', ring: 'ring-orange-700/20', text: 'JV' },
  c:     { bg: 'bg-gray-600',   ring: 'ring-gray-600/20',   text: 'C' },
  cpp:   { bg: 'bg-blue-700',   ring: 'ring-blue-700/20',   text: 'C++' },
  h:     { bg: 'bg-gray-500',   ring: 'ring-gray-500/20',   text: 'H' },
  html:  { bg: 'bg-orange-500', ring: 'ring-orange-500/20', text: 'HTM' },
  css:   { bg: 'bg-blue-400',   ring: 'ring-blue-400/20',   text: 'CSS' },
  json:  { bg: 'bg-yellow-600', ring: 'ring-yellow-600/20', text: 'JSN' },
  yaml:  { bg: 'bg-pink-500',   ring: 'ring-pink-500/20',   text: 'YML' },
  yml:   { bg: 'bg-pink-500',   ring: 'ring-pink-500/20',   text: 'YML' },
  toml:  { bg: 'bg-gray-600',   ring: 'ring-gray-600/20',   text: 'TML' },
  png:   { bg: 'bg-purple-500', ring: 'ring-purple-500/20', text: 'PNG' },
  jpg:   { bg: 'bg-purple-500', ring: 'ring-purple-500/20', text: 'JPG' },
  jpeg:  { bg: 'bg-purple-500', ring: 'ring-purple-500/20', text: 'JPG' },
  gif:   { bg: 'bg-pink-400',   ring: 'ring-pink-400/20',   text: 'GIF' },
  svg:   { bg: 'bg-green-400',  ring: 'ring-green-400/20',  text: 'SVG' },
  eml:   { bg: 'bg-indigo-500', ring: 'ring-indigo-500/20', text: 'EML' },
  ipynb: { bg: 'bg-orange-500', ring: 'ring-orange-500/20', text: 'NB' },
  sh:    { bg: 'bg-gray-600',   ring: 'ring-gray-600/20',   text: 'SH' },
  bash:  { bg: 'bg-gray-600',   ring: 'ring-gray-600/20',   text: 'SH' },
  sql:   { bg: 'bg-teal-500',   ring: 'ring-teal-500/20',   text: 'SQL' },
  r:     { bg: 'bg-blue-600',   ring: 'ring-blue-600/20',   text: 'R' },
};

function FileTypeIcon({ type }: { type: string }) {
  const style = FILE_TYPE_STYLES[type.toLowerCase()] ?? { bg: 'bg-gray-500', ring: 'ring-gray-500/20', text: type.toUpperCase().slice(0, 3) };
  return (
    <div className={`w-10 h-10 rounded-xl ${style.bg} ring-4 ${style.ring} flex items-center justify-center flex-shrink-0 shadow-sm`}>
      <span className="text-white text-[10px] font-bold tracking-wide leading-none">{style.text}</span>
    </div>
  );
}

function getScoreLabel(score: number): { label: string; className: string; icon: string } {
  if (score >= 0.8) return { label: 'Excellent', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/20', icon: 'M5 13l4 4L19 7' };
  if (score >= 0.5) return { label: 'Good', className: 'bg-accent-blue/10 text-accent-blue ring-1 ring-accent-blue/20', icon: 'M5 13l4 4L19 7' };
  return { label: 'Partial', className: 'bg-gray-500/10 text-gray-500 dark:text-gray-400 ring-1 ring-gray-500/20', icon: 'M20 12H4' };
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  if (diffDays < 365) return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatSize(bytes?: number): string | null {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function shortenPath(path: string): string {
  return path.replace(/^\/Users\/[^/]+/, '~');
}

function highlightSnippet(snippet: string, query: string): string {
  if (!query.trim()) return snippet;
  const words = query.trim()
    .split(/\s+/)
    .filter(w => w.length >= 2)
    .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!words.length) return snippet;
  const pattern = new RegExp(`(${words.join('|')})`, 'gi');
  return snippet.replace(
    pattern,
    '<mark class="bg-amber-200/80 dark:bg-amber-500/25 text-amber-900 dark:text-amber-200 rounded-sm px-0.5 font-medium not-italic">$1</mark>'
  );
}

// Related docs mini-list
function RelatedDocs({ docs, onOpen }: { docs: RelatedDoc[]; onOpen: (path: string) => void }) {
  if (!docs || docs.length === 0) return null;
  return (
    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-dark-border">
      <div className="flex items-center gap-1.5 mb-2">
        <svg className="w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
        <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">Similar</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {docs.slice(0, 3).map(doc => (
          <button
            key={doc.doc_id}
            onClick={(e) => { e.stopPropagation(); onOpen(doc.path); }}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 bg-gray-50 dark:bg-dark-hover border border-gray-100 dark:border-dark-border rounded-lg hover:border-accent-blue/40 hover:text-accent-blue transition-all duration-150 text-gray-500 dark:text-gray-400 max-w-[200px]"
            title={`${doc.filename} (${Math.round(doc.similarity * 100)}% similar)`}
          >
            <span className="truncate">{doc.filename}</span>
            <span className="flex-shrink-0 text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">{Math.round(doc.similarity * 100)}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}

interface ResultCardProps {
  result: RichSearchResult;
  query: string;
  focused?: boolean;
  onOpen?: () => void;
}

export default function ResultCard({ result, query, focused = false, onOpen }: ResultCardProps) {
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const { label: scoreLabel, className: scoreClass } = getScoreLabel(result.score);
  const dateStr = formatDate(result.modified);
  const sizeStr = formatSize(result.file_size);
  const highlightedSnippet = highlightSnippet(result.snippet, query);

  const docIdNum = typeof result.doc_id === 'string' ? parseInt(result.doc_id, 10) : result.doc_id;

  const handleCopyPath = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(result.path);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleClick = () => {
    fetch(`${API_BASE_URL}/api/open/${encodeURIComponent(result.path)}`);
    fetch(`${API_BASE_URL}/api/analytics/click`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, path: result.path, filename: result.filename }),
    }).catch(() => {});
    onOpen?.();
  };

  const handlePreview = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowPreview(true);
  };

  const openRelated = (path: string) => {
    fetch(`${API_BASE_URL}/api/open/${encodeURIComponent(path)}`);
  };

  return (
    <>
      <div
        onClick={handleClick}
        className={`result-card group p-4 sm:p-5 bg-white dark:bg-dark-surface border rounded-2xl
          cursor-pointer
          ${focused
            ? 'border-accent-blue ring-2 ring-accent-blue/20 shadow-md'
            : 'border-gray-100 dark:border-dark-border hover:border-gray-200 dark:hover:border-dark-hover'
          }`}
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter') handleClick(); }}
      >
        <div className="flex items-start gap-3 sm:gap-4">
          {/* File type icon */}
          <FileTypeIcon type={result.file_type} />

          <div className="flex-1 min-w-0">
            {/* Header row */}
            <div className="flex items-center gap-2.5 mb-1.5 flex-wrap">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate text-[15px] leading-snug">
                {result.filename}
              </h3>
              <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${scoreClass}`}>
                {scoreLabel} · {Math.round(result.score * 100)}%
              </span>
            </div>

            {/* Path */}
            <p className="text-xs text-gray-400 dark:text-gray-500 truncate mb-2.5 font-mono" title={result.path}>
              {shortenPath(result.path)}
            </p>

            {/* Snippet */}
            <p
              className="text-sm text-gray-600 dark:text-gray-300 line-clamp-2 leading-relaxed"
              dangerouslySetInnerHTML={{ __html: highlightedSnippet }}
            />

            {/* Footer: metadata badges + actions */}
            <div className="flex items-center gap-2 mt-3">
              {dateStr && (
                <span className="inline-flex items-center gap-1.5 text-[11px] text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-dark-hover px-2.5 py-1 rounded-lg">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  {dateStr}
                </span>
              )}
              {sizeStr && (
                <span className="inline-flex items-center gap-1.5 text-[11px] text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-dark-hover px-2.5 py-1 rounded-lg">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7" />
                  </svg>
                  {sizeStr}
                </span>
              )}

              {/* Actions — visible on hover */}
              <div className="ml-auto flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <button
                  onClick={handlePreview}
                  className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-accent-blue transition-colors px-2.5 py-1 rounded-lg hover:bg-accent-blue/5"
                  title="Quick preview"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                  Preview
                </button>

                <div className="w-px h-3.5 bg-gray-200 dark:bg-dark-border" />

                <button
                  onClick={handleCopyPath}
                  className="text-[11px] text-gray-400 hover:text-accent-blue transition-all flex items-center gap-1 px-2.5 py-1 rounded-lg hover:bg-accent-blue/5"
                >
                  {copied ? (
                    <>
                      <svg className="w-3 h-3 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="text-emerald-500">Copied</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      Copy path
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Related documents */}
            {result.related_docs && result.related_docs.length > 0 && (
              <RelatedDocs docs={result.related_docs} onOpen={openRelated} />
            )}
          </div>
        </div>
      </div>

      {/* Document preview slide-out */}
      {showPreview && (
        <DocumentPreviewPanel
          docId={isNaN(docIdNum) ? null : docIdNum}
          filename={result.filename}
          path={result.path}
          fileType={result.file_type}
          onClose={() => setShowPreview(false)}
        />
      )}
    </>
  );
}
