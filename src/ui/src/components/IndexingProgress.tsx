import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../config';
import type { IndexingProgress as IndexingProgressType } from '../types';

// Map technical phase names to human-readable descriptions
function describePhase(status: string, file?: string | null, message?: string): string {
  const name = file ? file.split('/').pop() : '';
  switch (status?.toLowerCase()) {
    case 'parsing':
      return name ? `Reading "${name}"` : 'Reading your files…';
    case 'embedding':
      return message || 'Understanding your files…';
    case 'storing':
      return 'Saving to index…';
    case 'discovery':
      return message || 'Finding files to index…';
    case 'complete':
      return message || 'Indexing complete';
    case 'error':
      return message ? `Error: ${message}` : 'An error occurred';
    case 'skipped':
      return name ? `Skipped "${name}"` : 'Skipped file';
    default:
      return name ? `Processing "${name}"` : 'Working…';
  }
}

interface IndexingProgressProps {
  isIndexing: boolean;
}

export default function IndexingProgress({ isIndexing }: IndexingProgressProps) {
  const [progress, setProgress] = useState<IndexingProgressType | null>(null);
  const [startTime] = useState(() => Date.now());
  const [completeSummary, setCompleteSummary] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!isIndexing) {
      // Keep the completion message briefly, then clear
      if (completeSummary) {
        const timer = setTimeout(() => {
          setCompleteSummary(null);
          setProgress(null);
        }, 5000);
        return () => clearTimeout(timer);
      }
      setProgress(null);
      return;
    }

    setCompleteSummary(null);

    // Build the WS URL: the backend endpoint is /ws/index-progress
    const wsUrl = API_BASE_URL.replace(/^http/, 'ws') + '/ws/index-progress';
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data: IndexingProgressType = JSON.parse(event.data);
        if (data.status === 'complete' && (!data.file || data.message?.startsWith('Done:'))) {
          // Final completion event — show summary
          const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
          setCompleteSummary(data.message || `Complete in ${elapsed}s`);
          setProgress(null);
        } else {
          setProgress(data);
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => {};
    ws.onclose = () => {};

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [isIndexing]);

  // Show completion summary briefly after indexing finishes
  if (!isIndexing && completeSummary) {
    return (
      <div className="max-w-3xl mx-auto px-3 sm:px-0 mb-3">
        <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800/50 rounded-xl p-3 sm:p-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-green-100 dark:bg-green-900/40 flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <span className="text-sm font-medium text-green-800 dark:text-green-300">
              {completeSummary}
            </span>
          </div>
        </div>
      </div>
    );
  }

  if (!isIndexing || !progress) {
    if (isIndexing) {
      // Indexing started but no WS data yet — show a spinner
      return (
        <div className="max-w-3xl mx-auto px-3 sm:px-0 mb-3">
          <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 rounded-xl p-3 sm:p-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center flex-shrink-0">
                <svg className="w-4 h-4 text-amber-500 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
              <span className="text-sm font-medium text-amber-800 dark:text-amber-300">
                Getting started…
              </span>
            </div>
          </div>
        </div>
      );
    }
    return null;
  }

  const isDiscovery = progress.status === 'discovery';
  const hasTotal = progress.total > 0;
  const percent = hasTotal && !isDiscovery
    ? Math.min(Math.round((progress.current / progress.total) * 100), 100)
    : null;

  const description = describePhase(progress.status, progress.file, progress.message);

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-0 mb-3">
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 rounded-xl p-3 sm:p-4">
        <div className="flex items-center gap-3">
          {/* Animated icon */}
          <div className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-amber-500 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="text-sm font-medium text-amber-800 dark:text-amber-300 truncate">
                {description}
              </span>
              {percent !== null && (
                <span className="text-xs text-amber-600 dark:text-amber-400 flex-shrink-0 tabular-nums">
                  {progress.current} of {progress.total} ({percent}%)
                </span>
              )}
            </div>

            {/* Progress bar */}
            <div className="w-full h-1.5 bg-amber-200 dark:bg-amber-800/50 rounded-full overflow-hidden">
              {percent !== null ? (
                <div
                  className="h-full bg-amber-500 dark:bg-amber-400 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${percent}%` }}
                />
              ) : (
                <div
                  className="h-full bg-amber-500 dark:bg-amber-400 rounded-full"
                  style={{
                    width: '30%',
                    animation: 'indeterminate 1.5s ease-in-out infinite',
                  }}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes indeterminate {
          0% { margin-left: 0%; width: 30%; }
          50% { margin-left: 40%; width: 40%; }
          100% { margin-left: 70%; width: 30%; }
        }
      `}</style>
    </div>
  );
}
