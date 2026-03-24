import type { IndexStatus } from '../types';

function formatLastIndexed(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return 'Updated just now';
  if (diffMin < 60) return `Updated ${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `Updated ${diffHrs}h ago`;
  return `Updated ${date.toLocaleDateString()}`;
}

function formatFileCount(n: number): string {
  if (n === 0) return 'No files indexed yet';
  if (n === 1) return '1 file ready';
  return `${n.toLocaleString()} files ready`;
}

interface StatusBarProps {
  status: IndexStatus | null;
  error: string | null;
}

export default function StatusBar({ status, error }: StatusBarProps) {
  // Error state
  if (error) {
    return (
      <>
        <div className="hidden sm:block fixed bottom-0 left-0 right-0 px-4 py-2 bg-red-50 dark:bg-red-950/40 border-t border-red-200 dark:border-red-900/50 z-10">
          <div className="max-w-5xl mx-auto flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
            <span className="text-xs text-red-600 dark:text-red-400 font-medium">
              DeskSearch isn't running
            </span>
            <span className="text-xs text-red-400 dark:text-red-500">
              &mdash; Open the DeskSearch app and try again
            </span>
          </div>
        </div>
        <div className="sm:hidden mx-3 mb-1 px-3 py-2 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 rounded-lg flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
          <span className="text-xs text-red-600 dark:text-red-400">DeskSearch isn't running</span>
        </div>
      </>
    );
  }

  if (!status) return null;

  const isIndexing = status.is_indexing;
  const fileCount = status.total_documents;
  const lastIndexed = formatLastIndexed(status.last_indexed);

  return (
    <>
      {/* Desktop status bar */}
      <div className="hidden sm:block fixed bottom-0 left-0 right-0 px-4 py-2 bg-white/80 dark:bg-dark-surface/80 backdrop-blur-md border-t border-gray-100 dark:border-dark-border z-10">
        <div className="max-w-5xl mx-auto flex items-center justify-between text-xs">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                isIndexing ? 'bg-amber-400 animate-pulse' : 'bg-emerald-500'
              }`} />
              <span className={`font-medium ${
                isIndexing
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-emerald-600 dark:text-emerald-400'
              }`}>
                {isIndexing ? 'Reading files...' : formatFileCount(fileCount)}
              </span>
            </div>

            {isIndexing && fileCount > 0 && (
              <span className="text-gray-400 dark:text-gray-500 tabular-nums">
                {fileCount.toLocaleString()} done so far
              </span>
            )}
          </div>

          {lastIndexed && !isIndexing && (
            <span className="text-gray-400 dark:text-gray-500">{lastIndexed}</span>
          )}
        </div>
      </div>

      {/* Mobile: compact inline status */}
      {(isIndexing || fileCount === 0) && (
        <div className="sm:hidden mx-3 mb-1 px-3 py-2 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-lg flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            isIndexing ? 'bg-amber-400 animate-pulse' : 'bg-gray-300'
          }`} />
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {isIndexing
              ? `Reading your files... ${fileCount > 0 ? `${fileCount.toLocaleString()} done` : ''}`
              : 'No files indexed yet \u2014 add a folder to get started'}
          </span>
        </div>
      )}
    </>
  );
}
