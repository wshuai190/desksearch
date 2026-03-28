import { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE_URL } from '../config';

interface ProgressData {
  state: 'idle' | 'discovering' | 'indexing' | 'complete' | 'error';
  phase: string;
  processed: number;
  total: number;
  percent: number;
  current_file: string;
  files_per_sec: number;
  elapsed_sec: number;
  errors: { file: string; message: string }[];
}

function formatElapsed(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function phaseLabel(phase: string): string {
  switch (phase) {
    case 'discovery': return 'Discovering files';
    case 'parsing': return 'Reading files';
    case 'embedding': return 'Generating embeddings';
    case 'storing': return 'Saving to index';
    default: return phase || 'Processing';
  }
}

interface IndexingProgressProps {
  isIndexing: boolean;
}

export default function IndexingProgress({ isIndexing }: IndexingProgressProps) {
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [showComplete, setShowComplete] = useState(false);
  const [completeSummary, setCompleteSummary] = useState('');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/index/status`);
      if (!res.ok) return;
      const data: ProgressData = await res.json();
      setProgress(data);

      if (data.state === 'complete') {
        const summary = `Indexed ${data.processed} files in ${formatElapsed(data.elapsed_sec)} (${data.files_per_sec} files/sec)`;
        setCompleteSummary(summary);
        setShowComplete(true);
        // Stop polling
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch {
      // ignore fetch errors
    }
  }, []);

  useEffect(() => {
    if (isIndexing) {
      setShowComplete(false);
      setCompleteSummary('');
      // Start polling at 1s interval
      poll();
      intervalRef.current = setInterval(poll, 1000);
      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      };
    } else {
      // When isIndexing goes false, do one final poll to get completion stats
      poll();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, [isIndexing, poll]);

  // Auto-hide completion message after 8s
  useEffect(() => {
    if (showComplete) {
      const timer = setTimeout(() => {
        setShowComplete(false);
        setProgress(null);
      }, 8000);
      return () => clearTimeout(timer);
    }
  }, [showComplete]);

  // Show completion banner
  if (showComplete && completeSummary) {
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

  // Nothing to show
  if (!progress || progress.state === 'idle') {
    if (isIndexing) {
      // Just started, no data yet
      return (
        <div className="max-w-3xl mx-auto px-3 sm:px-0 mb-3">
          <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 rounded-xl p-3 sm:p-4">
            <div className="flex items-center gap-3">
              <Spinner />
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

  // Error state
  if (progress.state === 'error') {
    return (
      <div className="max-w-3xl mx-auto px-3 sm:px-0 mb-3">
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/50 rounded-xl p-3 sm:p-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <span className="text-sm font-medium text-red-800 dark:text-red-300">
              Indexing failed — {progress.errors.length > 0 ? progress.errors[progress.errors.length - 1].message : 'Unknown error'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  const isDiscovery = progress.state === 'discovering';
  const hasPercent = progress.total > 0 && !isDiscovery;
  const percent = hasPercent ? Math.min(Math.round(progress.percent), 100) : null;

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-0 mb-3">
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 rounded-xl p-3 sm:p-4">
        <div className="flex items-center gap-3">
          <Spinner />
          <div className="flex-1 min-w-0">
            {/* Top row: phase + stats */}
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-sm font-medium text-amber-800 dark:text-amber-300 truncate">
                {phaseLabel(progress.phase)}
                {progress.current_file && (
                  <span className="font-normal text-amber-600 dark:text-amber-400">
                    {' — '}{progress.current_file}
                  </span>
                )}
              </span>
              {percent !== null && (
                <span className="text-xs text-amber-600 dark:text-amber-400 flex-shrink-0 tabular-nums font-medium">
                  {percent}%
                </span>
              )}
            </div>

            {/* Progress bar */}
            <div className="w-full h-1.5 bg-amber-200 dark:bg-amber-800/50 rounded-full overflow-hidden mb-1.5">
              {percent !== null ? (
                <div
                  className="h-full bg-amber-500 dark:bg-amber-400 rounded-full transition-all duration-700 ease-out"
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

            {/* Bottom row: detailed stats */}
            <div className="flex items-center gap-3 text-xs text-amber-600 dark:text-amber-500 tabular-nums">
              {hasPercent && (
                <span>{progress.processed} / {progress.total} files</span>
              )}
              {isDiscovery && progress.total > 0 && (
                <span>Found {progress.total} files</span>
              )}
              {progress.files_per_sec > 0 && (
                <span>{progress.files_per_sec} files/sec</span>
              )}
              {progress.elapsed_sec > 0 && (
                <span>{formatElapsed(progress.elapsed_sec)}</span>
              )}
              {progress.errors.length > 0 && (
                <span className="text-red-500">{progress.errors.length} error{progress.errors.length > 1 ? 's' : ''}</span>
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

function Spinner() {
  return (
    <div className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center flex-shrink-0">
      <svg className="w-4 h-4 text-amber-500 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>
  );
}
