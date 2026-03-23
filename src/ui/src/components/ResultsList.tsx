import { useState, useEffect, useRef, useCallback } from 'react';
import type { RichSearchResponse } from '../types';
import ResultCard from './ResultCard';
import NLAnswerBanner from './NLAnswerBanner';

// ── Skeleton loader ──────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="p-4 sm:p-5 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl animate-pulse">
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="w-7 h-7 bg-gray-200 dark:bg-dark-border rounded-lg mt-0.5 flex-shrink-0" />
        <div className="flex-1 space-y-2.5">
          {/* Filename */}
          <div className="h-4 bg-gray-200 dark:bg-dark-border rounded-md w-3/5" />
          {/* Badge + path */}
          <div className="flex gap-2">
            <div className="h-5 bg-gray-200 dark:bg-dark-border rounded-md w-20" />
            <div className="h-5 bg-gray-200 dark:bg-dark-border rounded-md w-32" />
          </div>
          {/* Snippet */}
          <div className="space-y-1.5">
            <div className="h-3.5 bg-gray-200 dark:bg-dark-border rounded w-full" />
            <div className="h-3.5 bg-gray-200 dark:bg-dark-border rounded w-5/6" />
            <div className="h-3.5 bg-gray-200 dark:bg-dark-border rounded w-4/6" />
          </div>
          {/* Date */}
          <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-28" />
        </div>
      </div>
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────
const SEARCH_TIPS = [
  'Try describing what the file is about, e.g. "project budget spreadsheet"',
  'Use natural language like "meeting notes from last month"',
  'Search by content, not filename — e.g. "invoice from Acme Corp"',
  'Broaden your search — remove specific dates or names',
];

function EmptyState({ query }: { query: string }) {
  return (
    <div className="text-center py-12 sm:py-16 px-4 animate-fadeIn">
      <div className="inline-flex items-center justify-center w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-gray-100 dark:bg-dark-border mb-4">
        <svg className="w-7 h-7 sm:w-8 sm:h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
      </div>
      <h3 className="text-base sm:text-lg font-semibold text-gray-800 dark:text-gray-200 mb-2">
        Nothing found for &ldquo;{query}&rdquo;
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-5">
        This exact wording didn't match anything. Try a different way to describe it.
      </p>
      <div className="text-left max-w-sm mx-auto space-y-2">
        {SEARCH_TIPS.map((tip, i) => (
          <div key={i} className="flex items-start gap-2 text-sm text-gray-500 dark:text-gray-400">
            <span className="text-accent-blue mt-0.5 flex-shrink-0">💡</span>
            <span>{tip}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Error state ──────────────────────────────────────────────────────────────
function ErrorState({ message }: { message: string }) {
  const isServerDown = message.toLowerCase().includes('fetch') ||
    message.toLowerCase().includes('network') ||
    message.toLowerCase().includes('connect');

  return (
    <div className="text-center py-10 sm:py-12 px-4 animate-fadeIn">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-50 dark:bg-red-900/20 mb-4">
        <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
      </div>
      <p className="text-base font-medium text-gray-700 dark:text-gray-300 mb-1">
        {isServerDown ? "Couldn't reach DeskSearch" : "Something went wrong"}
      </p>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        {isServerDown
          ? 'Make sure the DeskSearch app is running, then try again.'
          : 'Try refreshing the page. If this keeps happening, restart DeskSearch.'}
      </p>
    </div>
  );
}

// ── Search stats ─────────────────────────────────────────────────────────────
function SearchStats({ data, loading }: { data: RichSearchResponse; loading: boolean }) {
  const total = data.total;
  const ms = data.query_time_ms;
  const timeStr = ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;

  return (
    <div className="flex items-center justify-between mb-3 sm:mb-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        <span className="font-semibold text-gray-700 dark:text-gray-300">{total.toLocaleString()}</span>
        {' '}{total === 1 ? 'result' : 'results'}
        <span className="text-gray-400 dark:text-gray-500 hidden sm:inline"> · {timeStr}</span>
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

// ── Keyboard nav hint (desktop only) ─────────────────────────────────────────
function NavHint() {
  return (
    <div className="hidden sm:flex items-center gap-3 mt-5 justify-center text-xs text-gray-400 dark:text-gray-500">
      <span className="flex items-center gap-1">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">↑↓</kbd>
        Navigate
      </span>
      <span className="flex items-center gap-1">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">↵</kbd>
        Open file
      </span>
      <span className="flex items-center gap-1">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">Esc</kbd>
        New search
      </span>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
interface ResultsListProps {
  data: RichSearchResponse | null;
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

  useEffect(() => {
    setActiveIndex(-1);
    cardRefs.current = [];
  }, [data]);

  useEffect(() => {
    if (focusFirstResult && data?.results.length) {
      setActiveIndex(0);
      cardRefs.current[0]?.scrollIntoView({ block: 'nearest' });
      onFocusFirstResultConsumed?.();
    }
  }, [focusFirstResult, data, onFocusFirstResultConsumed]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!data?.results.length) return;
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
        if (result) fetch(`/api/open/${encodeURIComponent(result.path)}`);
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

  // Show skeletons on first load
  if (loading && !data) {
    return (
      <div>
        <div className="h-5 w-36 bg-gray-200 dark:bg-dark-border rounded animate-pulse mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
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
      {/* NL Answer banner — shown only for question queries */}
      {data.answer && (
        <NLAnswerBanner answer={data.answer} query={query} />
      )}

      <SearchStats data={data} loading={loading} />
      <div className="space-y-2 sm:space-y-3">
        {data.results.map((result, index) => (
          <div
            key={result.doc_id}
            ref={el => { cardRefs.current[index] = el; }}
            className="animate-fadeIn"
            style={{ animationDelay: `${Math.min(index * 25, 150)}ms` }}
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
