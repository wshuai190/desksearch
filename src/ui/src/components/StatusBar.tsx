import type { IndexStatus } from '../types';

function formatLastIndexed(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return date.toLocaleDateString();
}

interface StatusBarProps {
  status: IndexStatus | null;
  error: string | null;
}

export default function StatusBar({ status, error }: StatusBarProps) {
  if (error) {
    return (
      <div className="fixed bottom-0 left-0 right-0 px-4 py-2 bg-red-500/10 border-t border-red-500/20">
        <div className="max-w-5xl mx-auto flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-red-500" />
          <span className="text-xs text-red-400">Server disconnected</span>
        </div>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 px-4 py-2 bg-gray-50 dark:bg-dark-surface border-t border-gray-100 dark:border-dark-border">
      <div className="max-w-5xl mx-auto flex items-center justify-between text-xs text-gray-400 dark:text-gray-500">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${status.is_indexing ? 'bg-yellow-500 animate-pulse' : 'bg-green-500'}`} />
            <span>{status.is_indexing ? 'Indexing...' : 'Ready'}</span>
          </div>
          <span>{status.total_documents.toLocaleString()} files indexed</span>
          <span>{status.index_size_mb.toFixed(1)} MB</span>
        </div>
        <span>Last indexed: {formatLastIndexed(status.last_indexed)}</span>
      </div>
    </div>
  );
}
