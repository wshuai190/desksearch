import { useRef, useEffect, useState, useCallback, forwardRef, useImperativeHandle } from 'react';

const RECENT_SEARCHES_KEY = 'desksearch:recent-searches';
const MAX_RECENT = 8;

function getRecentSearches(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_SEARCHES_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveRecentSearch(query: string) {
  if (!query.trim() || query.trim().length < 2) return;
  const recent = getRecentSearches().filter(q => q !== query.trim());
  recent.unshift(query.trim());
  localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
}

// Example searches that rotate on each page load
const EXAMPLE_QUERIES = [
  'meeting notes from last month',
  'project budget spreadsheet',
  'invoice from Acme Corp',
  'Python script for data processing',
  'notes about quarterly review',
  'contract signed in 2023',
  'email about the conference',
  'todo list for the project',
];

function getExamples(): string[] {
  const seed = Math.floor(Date.now() / 60000);
  const shuffled = [...EXAMPLE_QUERIES].sort(() => {
    return Math.sin(seed * 9301 + EXAMPLE_QUERIES.indexOf(EXAMPLE_QUERIES[0])) - 0.5;
  });
  return shuffled.slice(0, 3);
}

// ── Quick stats shown on home screen ────────────────────────────────────────
function QuickStats({ fileCount, lastIndexed, indexSizeMb }: { fileCount?: number; lastIndexed?: string | null; indexSizeMb?: number }) {
  if (!fileCount || fileCount === 0) return null;

  const formatLastIndexed = (dateStr: string | null | undefined): string => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMin = Math.floor((now.getTime() - date.getTime()) / 60000);
    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHrs = Math.floor(diffMin / 60);
    if (diffHrs < 24) return `${diffHrs}h ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  const stats = [
    { label: 'Files indexed', value: fileCount.toLocaleString(), icon: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z' },
    { label: 'Last updated', value: formatLastIndexed(lastIndexed), icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
    ...(indexSizeMb && indexSizeMb > 0 ? [{ label: 'Index size', value: `${indexSizeMb.toFixed(1)} MB`, icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' }] : []),
  ];

  return (
    <div className="flex items-center justify-center gap-6 mt-6 animate-fadeIn" style={{ animationDelay: '100ms' }}>
      {stats.map((s) => (
        <div key={s.label} className="flex items-center gap-2 text-gray-400 dark:text-gray-500">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d={s.icon} />
          </svg>
          <span className="text-xs">
            <span className="font-medium text-gray-600 dark:text-gray-300">{s.value}</span>
            {' '}<span className="hidden sm:inline">{s.label.toLowerCase()}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Search tips for home screen ─────────────────────────────────────────────
function SearchTips() {
  const tips = [
    { icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.347.346A3.5 3.5 0 0114.5 20.5H9.5a3.5 3.5 0 01-2.471-1.026l-.347-.346z', text: 'Search by meaning, not just keywords' },
    { icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z', text: 'Filter by date, file type, or folder' },
    { icon: 'M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z', text: 'Use voice search or press / to focus' },
  ];

  return (
    <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-6 mt-6 animate-fadeIn" style={{ animationDelay: '200ms' }}>
      {tips.map((tip, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d={tip.icon} />
          </svg>
          <span>{tip.text}</span>
        </div>
      ))}
    </div>
  );
}

// ── Hero section shown above the search bar when centered ──────────────────
interface CenteredHeroProps {
  fileCount?: number;
  isIndexing?: boolean;
  onExampleClick: (q: string) => void;
}

function CenteredHero({ fileCount, isIndexing, onExampleClick }: CenteredHeroProps) {
  const [examples] = useState(getExamples);

  const hasFiles = fileCount !== undefined && fileCount > 0;
  const noFiles = fileCount !== undefined && fileCount === 0 && !isIndexing;

  return (
    <div className="text-center mb-8 sm:mb-10 px-2">
      {/* Logo icon */}
      <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-accent-blue to-blue-600 shadow-lg shadow-accent-blue/20 mb-5">
        <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>

      {/* Title */}
      <h1 className="text-3xl sm:text-4xl font-bold mb-2 text-gray-900 dark:text-gray-50 tracking-tight">
        DeskSearch
      </h1>

      {/* Subtitle — context-aware */}
      {isIndexing && (
        <p className="text-gray-500 dark:text-gray-400 text-base sm:text-lg mb-4">
          <span className="inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse inline-block" />
            Reading your files... you can already start searching!
          </span>
        </p>
      )}

      {noFiles && (
        <div className="mb-4 space-y-2">
          <p className="text-gray-500 dark:text-gray-400 text-base sm:text-lg">
            No files indexed yet
          </p>
          <p className="text-sm text-gray-400 dark:text-gray-500">
            Go to the <strong className="text-gray-600 dark:text-gray-300">Folders</strong> tab and add a folder to get started.
          </p>
        </div>
      )}

      {!isIndexing && !noFiles && (
        <p className="text-gray-500 dark:text-gray-400 text-base sm:text-lg mb-4">
          {hasFiles
            ? `Search ${fileCount!.toLocaleString()} files by meaning`
            : 'Search your files by meaning, not just keywords'}
        </p>
      )}

      {/* Example queries — only show when there are files */}
      {hasFiles && !isIndexing && (
        <div className="mt-5 sm:mt-6">
          <p className="text-[11px] text-gray-400 dark:text-gray-500 mb-2.5 uppercase tracking-widest font-medium">
            Try searching for
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {examples.map((q) => (
              <button
                key={q}
                onClick={() => onExampleClick(q)}
                className="text-sm px-3.5 py-1.5 rounded-full border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:border-accent-blue hover:text-accent-blue dark:hover:text-accent-blue hover:bg-accent-blue/5 transition-all duration-200"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main SearchBar component ───────────────────────────────────────────────
interface SearchBarProps {
  query: string;
  onQueryChange: (query: string) => void;
  centered: boolean;
  onArrowDown?: () => void;
  fileCount?: number;
  isIndexing?: boolean;
  lastIndexed?: string | null;
  indexSizeMb?: number;
}

export interface SearchBarHandle {
  focus: () => void;
}

const SearchBar = forwardRef<SearchBarHandle, SearchBarProps>(
  ({ query, onQueryChange, centered, onArrowDown, fileCount, isIndexing, lastIndexed, indexSizeMb }, ref) => {
    const inputRef = useRef<HTMLInputElement>(null);
    const [recentSearches, setRecentSearches] = useState<string[]>([]);
    const [showRecent, setShowRecent] = useState(false);
    const [isListening, setIsListening] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);
    const commitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useImperativeHandle(ref, () => ({
      focus: () => {
        inputRef.current?.focus();
        inputRef.current?.select();
      },
    }));

    useEffect(() => {
      inputRef.current?.focus();
    }, []);

    // Save to recent searches when query settles
    useEffect(() => {
      if (commitTimerRef.current) clearTimeout(commitTimerRef.current);
      if (query.trim().length >= 2) {
        commitTimerRef.current = setTimeout(() => {
          saveRecentSearch(query);
          setRecentSearches(getRecentSearches());
        }, 1200);
      }
      return () => { if (commitTimerRef.current) clearTimeout(commitTimerRef.current); };
    }, [query]);

    const handleFocus = () => {
      setRecentSearches(getRecentSearches());
      if (!query) setShowRecent(true);
    };

    const handleBlur = () => {
      setTimeout(() => setShowRecent(false), 150);
    };

    // Global keyboard shortcuts
    useEffect(() => {
      const handleKeyDown = (e: KeyboardEvent) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
          e.preventDefault();
          inputRef.current?.focus();
          inputRef.current?.select();
          return;
        }
        if (e.key === '/' && document.activeElement !== inputRef.current) {
          const tag = (document.activeElement as HTMLElement)?.tagName;
          if (tag !== 'INPUT' && tag !== 'TEXTAREA') {
            e.preventDefault();
            inputRef.current?.focus();
          }
          return;
        }
        if (e.key === 'Escape' && document.activeElement === inputRef.current) {
          onQueryChange('');
          setShowRecent(false);
          inputRef.current?.blur();
        }
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onQueryChange]);

    const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setShowRecent(false);
        onArrowDown?.();
      }
      if (e.key === 'Escape') setShowRecent(false);
    };

    // Voice search
    const handleVoiceSearch = useCallback(() => {
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (!SpeechRecognition) {
        alert('Voice search is not supported in this browser.');
        return;
      }
      const recognition = new SpeechRecognition();
      recognition.lang = navigator.language || 'en-US';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      setIsListening(true);
      recognition.start();

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        onQueryChange(transcript);
        saveRecentSearch(transcript);
        setRecentSearches(getRecentSearches());
        setIsListening(false);
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);
    }, [onQueryChange]);

    const hasSpeechRecognition =
      typeof window !== 'undefined' &&
      ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window);

    const clearRecentSearch = (e: React.MouseEvent, searchQuery: string) => {
      e.stopPropagation();
      const updated = getRecentSearches().filter(q => q !== searchQuery);
      localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(updated));
      setRecentSearches(updated);
    };

    return (
      <div
        ref={containerRef}
        className={`w-full transition-all duration-500 relative ${centered ? 'max-w-xl' : 'max-w-3xl'}`}
      >
        {/* Hero section for centered/home view */}
        {centered && (
          <CenteredHero
            fileCount={fileCount}
            isIndexing={isIndexing}
            onExampleClick={(q) => { onQueryChange(q); setShowRecent(false); }}
          />
        )}

        {/* Search input */}
        <div className="relative group">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <svg
              className="h-5 w-5 text-gray-400 group-focus-within:text-accent-blue transition-colors duration-200"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
          </div>

          <input
            ref={inputRef}
            type="search"
            inputMode="search"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck="false"
            value={query}
            onChange={(e) => {
              onQueryChange(e.target.value);
              if (e.target.value === '') setShowRecent(true);
              else setShowRecent(false);
            }}
            onKeyDown={handleInputKeyDown}
            onFocus={handleFocus}
            onBlur={handleBlur}
            placeholder={isListening ? 'Listening...' : 'Search your files...'}
            className={`search-input w-full bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
              rounded-2xl pl-12 text-gray-900 dark:text-gray-100
              placeholder-gray-400 dark:placeholder-gray-500
              focus:outline-none focus:border-accent-blue/50
              ${centered ? 'py-4 text-lg' : 'py-3 text-base'}
              ${hasSpeechRecognition ? 'pr-20' : 'pr-10'}`}
          />

          <div className="absolute inset-y-0 right-0 pr-3 flex items-center gap-1">
            {/* Voice search */}
            {hasSpeechRecognition && (
              <button
                onClick={handleVoiceSearch}
                className={`p-1.5 rounded-lg transition-all duration-200 ${
                  isListening
                    ? 'text-red-500 bg-red-50 dark:bg-red-900/20 animate-pulse'
                    : 'text-gray-400 hover:text-accent-blue hover:bg-gray-100 dark:hover:bg-dark-hover'
                }`}
                title={isListening ? 'Listening...' : 'Search by voice'}
                aria-label="Voice search"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </button>
            )}

            {/* Keyboard hint (desktop only when empty) */}
            {!query && !isListening && (
              <div className="hidden sm:flex items-center gap-1">
                <kbd className="text-[11px] text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded-md font-mono border border-gray-200 dark:border-dark-border/50">⌘K</kbd>
              </div>
            )}

            {/* Clear button */}
            {query && (
              <button
                onClick={() => { onQueryChange(''); setShowRecent(true); inputRef.current?.focus(); }}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
                title="Clear (Esc)"
                aria-label="Clear search"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {/* Recent searches dropdown */}
        {showRecent && recentSearches.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl shadow-lg z-30 overflow-hidden animate-slideDown">
            <div className="px-4 py-2.5 text-[11px] text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-dark-border font-medium uppercase tracking-widest">
              Recent searches
            </div>
            {recentSearches.map((s) => (
              <button
                key={s}
                className="w-full text-left px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-hover flex items-center gap-3 group/item transition-colors"
                onMouseDown={(e) => {
                  e.preventDefault();
                  onQueryChange(s);
                  setShowRecent(false);
                }}
              >
                <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="flex-1 truncate">{s}</span>
                <span
                  className="opacity-0 group-hover/item:opacity-100 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-base leading-none px-1 transition-opacity"
                  onClick={(e) => clearRecentSearch(e, s)}
                  title="Remove"
                >
                  &times;
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Bottom info for centered view */}
        {centered && (
          <>
            {/* Keyboard hint */}
            <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-3 hidden sm:block">
              Press <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded-md font-mono text-[11px] border border-gray-200 dark:border-dark-border/50">⌘K</kbd> or{' '}
              <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded-md font-mono text-[11px] border border-gray-200 dark:border-dark-border/50">/</kbd> to focus anytime
            </p>

            {/* Quick stats */}
            <QuickStats fileCount={fileCount} lastIndexed={lastIndexed} indexSizeMb={indexSizeMb} />

            {/* Search tips */}
            <SearchTips />
          </>
        )}
      </div>
    );
  }
);

SearchBar.displayName = 'SearchBar';
export default SearchBar;
