import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import type { RichSearchResponse, RichSearchResult } from '../types';
import ResultCard from './ResultCard';
import NLAnswerBanner from './NLAnswerBanner';

// ── Sort options ────────────────────────────────────────────────────────────
type SortOption = 'relevance' | 'date-newest' | 'date-oldest' | 'size-largest' | 'size-smallest' | 'type';

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'relevance',     label: 'Relevance' },
  { value: 'date-newest',   label: 'Date (newest)' },
  { value: 'date-oldest',   label: 'Date (oldest)' },
  { value: 'size-largest',  label: 'Size (largest)' },
  { value: 'size-smallest', label: 'Size (smallest)' },
  { value: 'type',          label: 'File type' },
];

function sortResults(results: RichSearchResult[], sort: SortOption): RichSearchResult[] {
  if (sort === 'relevance') return results;
  const sorted = [...results];
  switch (sort) {
    case 'date-newest':
      return sorted.sort((a, b) => {
        if (!a.modified) return 1;
        if (!b.modified) return -1;
        return new Date(b.modified).getTime() - new Date(a.modified).getTime();
      });
    case 'date-oldest':
      return sorted.sort((a, b) => {
        if (!a.modified) return 1;
        if (!b.modified) return -1;
        return new Date(a.modified).getTime() - new Date(b.modified).getTime();
      });
    case 'size-largest':
      return sorted.sort((a, b) => (b.file_size ?? 0) - (a.file_size ?? 0));
    case 'size-smallest':
      return sorted.sort((a, b) => (a.file_size ?? 0) - (b.file_size ?? 0));
    case 'type':
      return sorted.sort((a, b) => a.file_type.localeCompare(b.file_type));
    default:
      return sorted;
  }
}

// ── Skeleton loader ──────────────────────────────────────────────────────────
function SkeletonCard({ delay = 0 }: { delay?: number }) {
  return (
    <div
      className="p-4 sm:p-5 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-2xl animate-fadeIn"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start gap-3 sm:gap-4">
        {/* File icon skeleton */}
        <div className="w-9 h-9 skeleton rounded-lg flex-shrink-0" />
        <div className="flex-1 space-y-3">
          {/* Filename + badge */}
          <div className="flex items-center gap-2">
            <div className="h-4 skeleton rounded-md w-48" />
            <div className="h-5 skeleton rounded-md w-16" />
          </div>
          {/* Path */}
          <div className="h-3 skeleton rounded w-36" />
          {/* Snippet lines */}
          <div className="space-y-2">
            <div className="h-3.5 skeleton rounded w-full" />
            <div className="h-3.5 skeleton rounded w-4/5" />
          </div>
          {/* Footer badges */}
          <div className="flex gap-2 pt-1">
            <div className="h-5 skeleton rounded-md w-16" />
            <div className="h-5 skeleton rounded-md w-14" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────
const SEARCH_TIPS = [
  'Try describing what the file is about, e.g. "project budget spreadsheet"',
  'Use natural language like "meeting notes from last month"',
  'Search by content, not filename \u2014 e.g. "invoice from Acme Corp"',
  'Broaden your search \u2014 remove specific dates or names',
];

function EmptyState({ query }: { query: string }) {
  return (
    <div className="text-center py-16 sm:py-20 px-4 animate-fadeIn">
      {/* Empty state illustration */}
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gray-100 dark:bg-dark-surface border border-gray-200 dark:border-dark-border mb-5">
        <svg className="w-8 h-8 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m5.231 13.481L15 17.25m-4.5-15H5.625c-.621 0-1.125.504-1.125 1.125v16.5c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9zm3.75 11.625a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-2">
        No results for &ldquo;{query}&rdquo;
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-sm mx-auto">
        Try describing your file differently. DeskSearch understands meaning, so a different phrasing might find what you need.
      </p>

      {/* Tips */}
      <div className="text-left max-w-sm mx-auto space-y-2.5">
        <p className="text-[11px] text-gray-400 uppercase tracking-widest font-medium mb-3">Search tips</p>
        {SEARCH_TIPS.map((tip, i) => (
          <div key={i} className="flex items-start gap-2.5 text-sm text-gray-500 dark:text-gray-400">
            <svg className="w-4 h-4 text-accent-blue flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.347.346A3.5 3.5 0 0114.5 20.5H9.5a3.5 3.5 0 01-2.471-1.026l-.347-.346z" />
            </svg>
            <span>{tip}</span>
          </div>
        ))}
      </div>

      {/* CTA */}
      <button
        onClick={() => {
          const input = document.querySelector('input[type="search"]') as HTMLInputElement;
          if (input) { input.value = ''; input.focus(); input.dispatchEvent(new Event('input', { bubbles: true })); }
        }}
        className="mt-8 px-5 py-2.5 bg-accent-blue text-white text-sm font-medium rounded-xl hover:bg-accent-blue-hover transition-all duration-200 shadow-sm hover:shadow-md"
      >
        Try a new search
      </button>
    </div>
  );
}

// ── Error state ──────────────────────────────────────────────────────────────
function ErrorState({ message }: { message: string }) {
  const isServerDown = message.toLowerCase().includes('fetch') ||
    message.toLowerCase().includes('network') ||
    message.toLowerCase().includes('connect');

  return (
    <div className="text-center py-16 sm:py-20 px-4 animate-fadeIn">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-red-50 dark:bg-red-900/20 mb-5">
        <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          {isServerDown ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m0-10.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.75c0 5.592 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.57-.598-3.75h-.152c-3.196 0-6.1-1.249-8.25-3.286zm0 13.036h.008v.008H12v-.008z" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          )}
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-2">
        {isServerDown ? "Can't reach DeskSearch" : "Something went wrong"}
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
        {isServerDown
          ? 'Make sure the DeskSearch app is running, then try again.'
          : 'Try refreshing the page. If this keeps happening, restart DeskSearch.'}
      </p>
      <button
        onClick={() => window.location.reload()}
        className="mt-6 px-5 py-2.5 bg-gray-100 dark:bg-dark-hover text-gray-700 dark:text-gray-200 text-sm font-medium rounded-xl hover:bg-gray-200 dark:hover:bg-dark-border transition-colors"
      >
        Refresh page
      </button>
    </div>
  );
}

// ── Search stats + sort dropdown ────────────────────────────────────────────
function SearchStats({ data, loading, sort, onSortChange }: {
  data: RichSearchResponse;
  loading: boolean;
  sort: SortOption;
  onSortChange: (s: SortOption) => void;
}) {
  const total = data.total;
  const ms = data.query_time_ms;
  const timeStr = ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;

  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-2">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          <span className="font-semibold text-gray-700 dark:text-gray-300 tabular-nums">{total.toLocaleString()}</span>
          {' '}{total === 1 ? 'result' : 'results'}
          <span className="text-gray-400 dark:text-gray-500 hidden sm:inline"> &middot; {timeStr}</span>
        </p>
        {loading && (
          <div className="w-3.5 h-3.5 border-2 border-accent-blue/30 border-t-accent-blue rounded-full animate-spin" />
        )}
      </div>

      {/* Sort dropdown */}
      <div className="relative">
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value as SortOption)}
          className="appearance-none text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-dark-hover border border-gray-200 dark:border-dark-border rounded-xl pl-3 pr-7 py-2 focus:outline-none focus:ring-1 focus:ring-accent-blue/50 focus:border-accent-blue cursor-pointer transition-colors hover:border-gray-300 dark:hover:border-dark-border"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <svg className="w-3.5 h-3.5 text-gray-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
}

// ── Keyboard nav hint (desktop only) ─────────────────────────────────────────
function NavHint() {
  return (
    <div className="hidden sm:flex items-center gap-4 mt-6 justify-center text-xs text-gray-400 dark:text-gray-500">
      <span className="flex items-center gap-1.5">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded-md font-mono text-[11px] border border-gray-200 dark:border-dark-border/50">↑↓</kbd>
        Navigate
      </span>
      <span className="flex items-center gap-1.5">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded-md font-mono text-[11px] border border-gray-200 dark:border-dark-border/50">Tab</kbd>
        Next result
      </span>
      <span className="flex items-center gap-1.5">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded-md font-mono text-[11px] border border-gray-200 dark:border-dark-border/50">↵</kbd>
        Open file
      </span>
      <span className="flex items-center gap-1.5">
        <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded-md font-mono text-[11px] border border-gray-200 dark:border-dark-border/50">Esc</kbd>
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
  const [sort, setSort] = useState<SortOption>('relevance');
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  const sortedResults = useMemo(() => {
    if (!data?.results) return [];
    return sortResults(data.results, sort);
  }, [data?.results, sort]);

  useEffect(() => {
    setActiveIndex(-1);
    cardRefs.current = [];
  }, [data]);

  useEffect(() => {
    if (focusFirstResult && sortedResults.length) {
      setActiveIndex(0);
      cardRefs.current[0]?.scrollIntoView({ block: 'nearest' });
      onFocusFirstResultConsumed?.();
    }
  }, [focusFirstResult, sortedResults, onFocusFirstResultConsumed]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!sortedResults.length) return;
      const tag = (document.activeElement as HTMLElement)?.tagName;
      const isTextInput = tag === 'TEXTAREA' || (tag === 'INPUT' && (document.activeElement as HTMLInputElement).type !== 'text');
      if (isTextInput) return;

      if (e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)) {
        // Don't hijack Tab if user is in a form field
        if (e.key === 'Tab' && (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA')) return;
        e.preventDefault();
        setActiveIndex(prev => {
          const next = Math.min(prev + 1, sortedResults.length - 1);
          cardRefs.current[next]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          return next;
        });
      } else if (e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)) {
        if (e.key === 'Tab' && (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA')) return;
        e.preventDefault();
        setActiveIndex(prev => {
          if (prev <= 0) return -1;
          const next = prev - 1;
          cardRefs.current[next]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          return next;
        });
      } else if (e.key === 'Enter' && activeIndex >= 0) {
        const result = sortedResults[activeIndex];
        if (result) fetch(`/api/open/${encodeURIComponent(result.path)}`);
      }
    },
    [sortedResults, activeIndex]
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
        <div className="flex items-center justify-between mb-4">
          <div className="h-5 w-32 skeleton rounded-lg" />
          <div className="h-7 w-28 skeleton rounded-lg" />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} delay={i * 60} />)}
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
      {/* NL Answer banner */}
      {data.answer && (
        <NLAnswerBanner answer={data.answer} query={query} />
      )}

      <SearchStats data={data} loading={loading} sort={sort} onSortChange={setSort} />
      <div className="space-y-2.5">
        {sortedResults.map((result, index) => (
          <div
            key={result.doc_id}
            ref={el => { cardRefs.current[index] = el; }}
            className="animate-fadeIn"
            style={{ animationDelay: `${Math.min(index * 30, 180)}ms` }}
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
      {sortedResults.length > 3 && <NavHint />}
    </div>
  );
}
