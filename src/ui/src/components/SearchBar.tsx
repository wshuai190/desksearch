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
  // Pick 3 random examples, stable per session
  const seed = Math.floor(Date.now() / 60000); // changes every minute
  const shuffled = [...EXAMPLE_QUERIES].sort(() => {
    return Math.sin(seed * 9301 + EXAMPLE_QUERIES.indexOf(EXAMPLE_QUERIES[0])) - 0.5;
  });
  return shuffled.slice(0, 3);
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
    <div className="text-center mb-6 sm:mb-8 px-2">
      {/* Title */}
      <h1 className="text-3xl sm:text-4xl font-bold mb-2 sm:mb-3 bg-gradient-to-r from-accent-blue to-blue-400 bg-clip-text text-transparent">
        <span role="img" aria-label="search">🔍</span> DeskSearch
      </h1>

      {/* Subtitle — context-aware */}
      {isIndexing && (
        <p className="text-gray-500 dark:text-gray-400 text-base sm:text-lg mb-4">
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse inline-block" />
            Reading your files… you can already start searching!
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
            ? `Search through ${fileCount!.toLocaleString()} files by meaning, not just keywords`
            : 'Search your files by meaning, not just keywords'}
        </p>
      )}

      {/* Example queries — only show when there are files */}
      {hasFiles && !isIndexing && (
        <div className="mt-4 sm:mt-5">
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-2 uppercase tracking-wide font-medium">
            Try searching for…
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {examples.map((q) => (
              <button
                key={q}
                onClick={() => onExampleClick(q)}
                className="tap-sm text-sm px-3 py-1.5 rounded-full border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 hover:border-accent-blue hover:text-accent-blue dark:hover:text-accent-blue hover:bg-accent-blue/5 transition-colors"
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
}

export interface SearchBarHandle {
  focus: () => void;
}

const SearchBar = forwardRef<SearchBarHandle, SearchBarProps>(
  ({ query, onQueryChange, centered, onArrowDown, fileCount, isIndexing }, ref) => {
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
        className={`w-full transition-all duration-500 relative ${centered ? 'max-w-2xl' : 'max-w-3xl'}`}
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
              className="h-5 w-5 text-gray-400 group-focus-within:text-accent-blue transition-colors"
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
            placeholder={isListening ? 'Listening…' : 'Search your files…'}
            className={`w-full bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
              rounded-xl pl-12 text-gray-900 dark:text-gray-100
              placeholder-gray-400 dark:placeholder-gray-500
              focus:outline-none focus:ring-2 focus:ring-accent-blue/50 focus:border-accent-blue
              transition-all ${centered ? 'py-4 text-lg' : 'py-3 text-base'}
              ${hasSpeechRecognition ? 'pr-20' : 'pr-10'}`}
          />

          <div className="absolute inset-y-0 right-0 pr-3 flex items-center gap-1">
            {/* Voice search */}
            {hasSpeechRecognition && (
              <button
                onClick={handleVoiceSearch}
                className={`tap-sm p-1.5 rounded-lg transition-colors ${
                  isListening
                    ? 'text-red-500 bg-red-50 dark:bg-red-900/20 animate-pulse'
                    : 'text-gray-400 hover:text-accent-blue hover:bg-gray-100 dark:hover:bg-dark-hover'
                }`}
                title={isListening ? 'Listening…' : 'Search by voice'}
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
                <kbd className="text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">⌘K</kbd>
              </div>
            )}

            {/* Clear button */}
            {query && (
              <button
                onClick={() => { onQueryChange(''); setShowRecent(true); inputRef.current?.focus(); }}
                className="tap-sm p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
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
          <div className="absolute top-full left-0 right-0 mt-1.5 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl shadow-lg z-30 overflow-hidden animate-slideDown">
            <div className="px-4 py-2 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-dark-border font-medium uppercase tracking-wide">
              Recent searches
            </div>
            {recentSearches.map((s) => (
              <button
                key={s}
                className="tap-sm w-full text-left px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-hover flex items-center gap-3 group/item"
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
                  className="opacity-0 group-hover/item:opacity-100 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-base leading-none px-1 transition-opacity tap-sm"
                  onClick={(e) => clearRecentSearch(e, s)}
                  title="Remove"
                >
                  ×
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Keyboard hint below (desktop, centered only) */}
        {centered && (
          <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-3 hidden sm:block">
            Press <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">⌘K</kbd> or{' '}
            <kbd className="bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">/</kbd> to focus anytime
          </p>
        )}
      </div>
    );
  }
);

SearchBar.displayName = 'SearchBar';
export default SearchBar;
