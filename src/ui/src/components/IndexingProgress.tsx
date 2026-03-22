import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { IndexingProgress as IndexingProgressType } from '../types';

interface IndexingProgressProps {
  isIndexing: boolean;
}

export default function IndexingProgress({ isIndexing }: IndexingProgressProps) {
  const [progress, setProgress] = useState<IndexingProgressType | null>(null);

  useEffect(() => {
    if (!isIndexing) {
      setProgress(null);
      return;
    }

    const wsUrl = API_BASE_URL.replace(/^http/, 'ws') + '/ws/indexing';
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      const data: IndexingProgressType = JSON.parse(event.data);
      setProgress(data);
    };

    ws.onerror = () => {
      // Silently ignore WebSocket errors - status bar still shows indexing state
    };

    return () => {
      ws.close();
    };
  }, [isIndexing]);

  if (!isIndexing || !progress) return null;

  const percent = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;

  return (
    <div className="w-full max-w-3xl mx-auto mb-4">
      <div className="bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-lg p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-600 dark:text-gray-300 font-medium">
            {progress.phase}
          </span>
          <span className="text-xs text-gray-400">
            {progress.current}/{progress.total} ({percent}%)
          </span>
        </div>
        <div className="w-full h-1.5 bg-gray-100 dark:bg-dark-border rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-blue rounded-full transition-all duration-300"
            style={{ width: `${percent}%` }}
          />
        </div>
        <p className="text-xs text-gray-400 mt-1.5 truncate">
          {progress.current_file}
        </p>
      </div>
    </div>
  );
}
