import { useState } from 'react';
import type { SearchResult } from '../types';

// SVG-based file type icons for crispness
const FILE_ICON_MAP: Record<string, { icon: string; color: string }> = {
  pdf:  { icon: '📄', color: 'text-red-500' },
  txt:  { icon: '📝', color: 'text-gray-500' },
  md:   { icon: '📝', color: 'text-blue-400' },
  doc:  { icon: '📄', color: 'text-blue-600' },
  docx: { icon: '📄', color: 'text-blue-600' },
  xls:  { icon: '📊', color: 'text-green-600' },
  xlsx: { icon: '📊', color: 'text-green-600' },
  csv:  { icon: '📊', color: 'text-green-500' },
  py:   { icon: '🐍', color: 'text-blue-500' },
  js:   { icon: '⚡', color: 'text-yellow-500' },
  ts:   { icon: '⚡', color: 'text-blue-500' },
  tsx:  { icon: '⚛️', color: 'text-blue-400' },
  jsx:  { icon: '⚛️', color: 'text-blue-400' },
  rs:   { icon: '🦀', color: 'text-orange-600' },
  go:   { icon: '🐹', color: 'text-cyan-500' },
  java: { icon: '☕', color: 'text-orange-700' },
  c:    { icon: '🔧', color: 'text-gray-600' },
  cpp:  { icon: '🔧', color: 'text-blue-700' },
  h:    { icon: '🔧', color: 'text-gray-500' },
  html: { icon: '🌐', color: 'text-orange-500' },
  css:  { icon: '🎨', color: 'text-blue-400' },
  json: { icon: '📋', color: 'text-yellow-600' },
  yaml: { icon: '📋', color: 'text-pink-500' },
  yml:  { icon: '📋', color: 'text-pink-500' },
  toml: { icon: '📋', color: 'text-gray-600' },
  png:  { icon: '🖼️', color: 'text-purple-500' },
  jpg:  { icon: '🖼️', color: 'text-purple-500' },
  jpeg: { icon: '🖼️', color: 'text-purple-500' },
  gif:  { icon: '🖼️', color: 'text-pink-400' },
  svg:  { icon: '🖼️', color: 'text-green-400' },
  eml:  { icon: '✉️', color: 'text-indigo-500' },
  ipynb:{ icon: '📓', color: 'text-orange-500' },
  sh:   { icon: '💻', color: 'text-gray-600' },
  bash: { icon: '💻', color: 'text-gray-600' },
  sql:  { icon: '🗄️', color: 'text-teal-500' },
  r:    { icon: '📊', color: 'text-blue-600' },
};

function getFileIcon(fileType: string): { icon: string; color: string } {
  return FILE_ICON_MAP[fileType.toLowerCase()] ?? { icon: '📄', color: 'text-gray-500' };
}

function getScoreLabel(score: number): { label: string; className: string } {
  if (score >= 0.8) return { label: 'High', className: 'bg-green-500/10 text-green-500 border-green-500/20' };
  if (score >= 0.5) return { label: 'Good', className: 'bg-blue-500/10 text-blue-400 border-blue-500/20' };
  return { label: 'Low', className: 'bg-gray-500/10 text-gray-400 border-gray-500/20' };
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  if (diffDays < 365) return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatSize(bytes: number | undefined): string | null {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function shortenPath(path: string): string {
  return path.replace(/^\/Users\/[^/]+/, '~');
}

/**
 * Highlight query terms in snippet with <mark> tags.
 * Only highlights words with 2+ characters to avoid noisy highlights.
 */
function highlightSnippet(snippet: string, query: string): string {
  if (!query.trim()) return snippet;
  const words = query.trim()
    .split(/\s+/)
    .filter(w => w.length >= 2)
    .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (words.length === 0) return snippet;
  const pattern = new RegExp(`(${words.join('|')})`, 'gi');
  return snippet.replace(
    pattern,
    '<mark class="bg-yellow-200 dark:bg-yellow-500/30 text-yellow-900 dark:text-yellow-200 rounded-sm px-0.5 font-medium not-italic">$1</mark>'
  );
}

interface ResultCardProps {
  result: SearchResult;
  query: string;
  focused?: boolean;
  onOpen?: () => void;
}

export default function ResultCard({ result, query, focused = false, onOpen }: ResultCardProps) {
  const [copied, setCopied] = useState(false);
  const { icon, color } = getFileIcon(result.file_type);
  const { label: scoreLabel, className: scoreClass } = getScoreLabel(result.score);
  const dateStr = formatDate(result.modified);
  const sizeStr = formatSize(result.file_size);
  const highlightedSnippet = highlightSnippet(result.snippet, query);

  const handleCopyPath = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(result.path);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleClick = () => {
    fetch(`/api/open/${encodeURIComponent(result.path)}`);
    onOpen?.();
  };

  return (
    <div
      onClick={handleClick}
      className={`group p-4 bg-white dark:bg-dark-surface border rounded-lg
        cursor-pointer transition-all
        ${focused
          ? 'border-accent-blue ring-2 ring-accent-blue/20 shadow-sm'
          : 'border-gray-100 dark:border-dark-border hover:border-accent-blue/30 dark:hover:border-accent-blue/30 hover:shadow-sm'
        }`}
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') handleClick(); }}
    >
      <div className="flex items-start gap-3">
        {/* File icon */}
        <span className={`text-xl mt-0.5 flex-shrink-0 leading-none ${color}`} role="img" aria-hidden>
          {icon}
        </span>

        <div className="flex-1 min-w-0">
          {/* Header row: filename + badges */}
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">
              {result.filename}
            </h3>
            <span className={`text-xs px-1.5 py-0.5 rounded border flex-shrink-0 ${scoreClass}`}>
              {scoreLabel} · {Math.round(result.score * 100)}%
            </span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 uppercase tracking-wide font-mono flex-shrink-0">
              {result.file_type}
            </span>
          </div>

          {/* Path */}
          <p className="text-xs text-gray-400 dark:text-gray-500 truncate mb-2" title={result.path}>
            {shortenPath(result.path)}
          </p>

          {/* Snippet with highlighted terms */}
          <p
            className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: highlightedSnippet }}
          />

          {/* Footer: date, size, copy */}
          <div className="flex items-center gap-3 mt-2.5">
            {dateStr && (
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                {dateStr}
              </span>
            )}
            {sizeStr && (
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                {sizeStr}
              </span>
            )}
            <button
              onClick={handleCopyPath}
              className="text-xs text-gray-400 hover:text-accent-blue opacity-0 group-hover:opacity-100 transition-all flex items-center gap-1 ml-auto"
            >
              {copied ? (
                <>
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  Copied!
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
      </div>
    </div>
  );
}
