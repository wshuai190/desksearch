import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { IndexingProgress as IndexingProgressType } from '../types';

// Map technical phase names to human-readable descriptions
function describePhase(phase: string, filename?: string): string {
  const name = filename ? filename.split('/').pop() : '';
  switch (phase?.toLowerCase()) {
    case 'parsing':
    case 'reading':
      return name ? `Reading "${name}"` : 'Reading your files…';
    case 'embedding':
    case 'indexing':
      return name ? `Understanding "${name}"` : 'Understanding your files…';
    case 'storing':
    case 'saving':
      return 'Saving to index…';
    case 'discovery':
    case 'scanning':
      return 'Finding files to index…';
    default:
      return name ? `Processing "${name}"` : 'Working…';
  }
}

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

    ws.onerror = () => {};

    return () => ws.close();
  }, [isIndexing]);

  if (!isIndexing) return null;

  const percent = progress && progress.total > 0
    ? Math.round((progress.current / progress.total) * 100)
    : null;

  const description = progress
    ? describePhase(progress.phase, progress.current_file)
    : 'Getting started…';

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
                  {progress!.current} of {progress!.total}
                </span>
              )}
            </div>

            {/* Progress bar */}
            <div className="w-full h-1.5 bg-amber-200 dark:bg-amber-800/50 rounded-full overflow-hidden">
              <div
                className="h-full bg-amber-500 dark:bg-amber-400 rounded-full transition-all duration-500 ease-out"
                style={{ width: percent !== null ? `${percent}%` : '100%', animation: percent === null ? 'pulse 1.5s ease-in-out infinite' : 'none' }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
