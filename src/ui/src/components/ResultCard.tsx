import { useState } from 'react';
import type { SearchResult } from '../types';

const FILE_ICONS: Record<string, string> = {
  pdf: '\uD83D\uDCC4',
  txt: '\uD83D\uDCDD',
  md: '\uD83D\uDCDD',
  doc: '\uD83D\uDCC4',
  docx: '\uD83D\uDCC4',
  xls: '\uD83D\uDCCA',
  xlsx: '\uD83D\uDCCA',
  csv: '\uD83D\uDCCA',
  py: '\uD83D\uDCBB',
  js: '\uD83D\uDCBB',
  ts: '\uD83D\uDCBB',
  tsx: '\uD83D\uDCBB',
  jsx: '\uD83D\uDCBB',
  rs: '\uD83D\uDCBB',
  go: '\uD83D\uDCBB',
  java: '\uD83D\uDCBB',
  c: '\uD83D\uDCBB',
  cpp: '\uD83D\uDCBB',
  h: '\uD83D\uDCBB',
  html: '\uD83C\uDF10',
  css: '\uD83C\uDF28\uFE0F',
  json: '\uD83D\uDCC1',
  yaml: '\uD83D\uDCC1',
  yml: '\uD83D\uDCC1',
  toml: '\uD83D\uDCC1',
  png: '\uD83D\uDDBC\uFE0F',
  jpg: '\uD83D\uDDBC\uFE0F',
  jpeg: '\uD83D\uDDBC\uFE0F',
  gif: '\uD83D\uDDBC\uFE0F',
  svg: '\uD83D\uDDBC\uFE0F',
  eml: '\uD83D\uDCE7',
};

function getFileIcon(fileType: string): string {
  return FILE_ICONS[fileType.toLowerCase()] ?? '\uD83D\uDCC4';
}

function getScoreColor(score: number): string {
  if (score >= 0.8) return 'bg-green-500/10 text-green-400 border-green-500/20';
  if (score >= 0.5) return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
  return 'bg-gray-500/10 text-gray-400 border-gray-500/20';
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return date.toLocaleDateString();
}

interface ResultCardProps {
  result: SearchResult;
}

export default function ResultCard({ result }: ResultCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopyPath = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(result.path);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleClick = () => {
    // Open file via API (which uses system default app)
    fetch(`/api/open/${encodeURIComponent(result.path)}`);
  };

  return (
    <div
      onClick={handleClick}
      className="group p-4 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border
        rounded-lg hover:border-accent-blue/30 dark:hover:border-accent-blue/30
        cursor-pointer transition-all hover:shadow-sm"
    >
      <div className="flex items-start gap-3">
        <span className="text-xl mt-0.5 flex-shrink-0" role="img">
          {getFileIcon(result.file_type)}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">
              {result.filename}
            </h3>
            <span className={`text-xs px-1.5 py-0.5 rounded border ${getScoreColor(result.score)}`}>
              {Math.round(result.score * 100)}
            </span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {result.file_type}
            </span>
          </div>

          <p className="text-sm text-gray-500 dark:text-gray-400 truncate mb-2">
            {result.path}
          </p>

          <p
            className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: result.snippet }}
          />

          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs text-gray-400">
              {formatDate(result.modified ?? '')}
            </span>
            <button
              onClick={handleCopyPath}
              className="text-xs text-gray-400 hover:text-accent-blue opacity-0 group-hover:opacity-100 transition-all flex items-center gap-1"
            >
              {copied ? (
                <>
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  Copied
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
