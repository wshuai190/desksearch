import { useState, useEffect, useRef, useCallback } from 'react';
import type { SearchResponse } from '../types';
import ResultCard from './ResultCard';

// ── Skeleton loader ──────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="p-4 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-lg animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-6 h-6 bg-gray-200 dark:bg-dark-border rounded mt-0.5 flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="flex gap-2 items-center">
            <div className="h-4 bg-gray-200 dark:bg-dark-border rounded w-2/5" />
            <div className="h-4 bg-gray-200 dark:bg-dark-border rounded w-12" />
            <div className="h-4 bg-gray-200 dark:bg-dark-border rounded w-10" />
          </div>
          <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-3/5" />
          <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-full" />
          <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-4/5" />
          <div className="flex gap-3 mt-1">
            <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-16" />
            <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-12" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────
function EmptyState({ query }: { query: string }) {
  return (
    <div className="text-center py-16 px-4 animate-fadeIn">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 dark:bg-dark-border mb-4">
        <svg className="w-8 h-8 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
      </div>
      <h3 className="text-base font-medium text-gray-700 dark:text-gray-300 mb-1">
        No results for &ldquo;{query}&rdquo;
      </h3>
      <p className="text-sm text-gray-400 dark:text-gray-500 max-w-xs mx-auto">
        Try different keywords, check your spelling, or broaden your search.
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        <span className="text-xs bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 px-2 py-1 rounded">
          💡 Tip: Use natural language like "meeting notes from last month"
        </span>
      </div>
    </div>
  );
}

// ── Error state ──────────────────────────────────────────────────────────────
function ErrorState({ message }: { message: string }) {
  return (
    <div className="text-center py-12 animate-fadeIn">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-50 dark:bg-red-900/20 mb-3">
        <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
      </div>
      <p className="text-sm text-gray-600 dark:text-gray-400">{message}</p>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Make sure the DeskSearch server is running</p>
    </div>
  );
}

// ── Search stats ─────────────────────────────────────────────────────────────
function SearchStats({ data, loading }: { data: SearchResponse; loading: boolean }) {
  const ms = data.query_time_ms;
  const timeStr = ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;
  const total = data.total;

  return (
    <div className="flex items-center justify-between mb-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        <span className="font-medium text-gray-700 dark:text-gray-300">{total.toLocaleString()}</span>
        {' '}{total === 1 ? 'result' : 'results'}
        {' '}·{' '}
        <span className="text-gray-400 dark:text-gray-500">{timeStr}</span>
      </p>
      {loading && (
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <div className="w-3 h-3 border-2 border-accent-blue/30 border-t-accent-blue rounded-full animate-spin" />
          Searching…
        </div>
      )}
    </div>
  );
}

// ── Keyboard nav hint ────────────────────────────────────────────────────────
function NavHint() {
  return (
    <div className="flex items-center gap-3 mt-4 justify-center text-xs text-gray-400 dark:text-gray-500">
      <span className="flex items-center gap-1">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">↑↓</kbd>
        Navigate
      </span>
      <span className="flex items-center gap-1">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">↵</kbd>
        Open
      </span>
      <span className="flex items-center gap-1">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">Esc</kbd>
        Clear
      </span>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
interface ResultsListProps {
  data: SearchResponse | null;
  loading: boolean;
  error: string | null;
  query: string;
  focusFirstResult?: boolean;
  onFocusFirstResultConsumed?: () => void;
}

export default function ResultsList({
  data,
  loading,
  error,
  query,
  focusFirstResult,
  onFocusFirstResultConsumed,
}: ResultsListProps) {
  const [activeIndex, setActiveIndex] = useState(-1);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Reset active index when results change
  useEffect(() => {
    setActiveIndex(-1);
    cardRefs.current = [];
  }, [data]);

  // Jump to first result when arrow-down pressed from search bar
  useEffect(() => {
    if (focusFirstResult && data?.results.length) {
      setActiveIndex(0);
      cardRefs.current[0]?.scrollIntoView({ block: 'nearest' });
      onFocusFirstResultConsumed?.();
    }
  }, [focusFirstResult, data, onFocusFirstResultConsumed]);

  // Global arrow-key navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!data?.results.length) return;
      // Don't intercept when typing in non-search inputs
      const tag = (document.activeElement as HTMLElement)?.tagName;
      const isTextInput = tag === 'TEXTAREA' || (tag === 'INPUT' && (document.activeElement as HTMLInputElement).type !== 'text');
      if (isTextInput) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex(prev => {
          const next = Math.min(prev + 1, data.results.length - 1);
          cardRefs.current[next]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          return next;
        });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex(prev => {
          if (prev <= 0) return -1;
          const next = prev - 1;
          cardRefs.current[next]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          return next;
        });
      } else if (e.key === 'Enter' && activeIndex >= 0) {
        const result = data.results[activeIndex];
        if (result) {
          fetch(`/api/open/${encodeURIComponent(result.path)}`);
        }
      }
    },
    [data, activeIndex]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!query.trim()) return null;

  if (error) return <ErrorState message={error} />;

  // Show skeleton loaders for first load (no prior data)
  if (loading && !data) {
    return (
      <div>
        <div className="h-6 w-48 bg-gray-200 dark:bg-dark-border rounded animate-pulse mb-4" />
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (data && data.results.length === 0) {
    return <EmptyState query={query} />;
  }

  if (!data) return null;

  return (
    <div>
      <SearchStats data={data} loading={loading} />
      <div className="space-y-2">
        {data.results.map((result, index) => (
          <div
            key={result.doc_id}
            ref={el => { cardRefs.current[index] = el; }}
            className="animate-fadeIn"
            style={{ animationDelay: `${Math.min(index * 30, 200)}ms` }}
          >
            <ResultCard
              result={result}
              query={query}
              focused={activeIndex === index}
              onOpen={() => setActiveIndex(-1)}
            />
          </div>
        ))}
      </div>
      {data.results.length > 3 && <NavHint />}
    </div>
  );
}
