import { useRef, useEffect } from 'react';

interface SearchBarProps {
  query: string;
  onQueryChange: (query: string) => void;
  centered: boolean;
}

export default function SearchBar({ query, onQueryChange, centered }: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Global keyboard shortcuts: '/' to focus, Escape to clear
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        onQueryChange('');
        inputRef.current?.blur();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onQueryChange]);

  return (
    <div className={`w-full transition-all duration-500 ${centered ? 'max-w-2xl' : 'max-w-3xl'}`}>
      {centered && (
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold mb-3 bg-gradient-to-r from-accent-blue to-blue-400 bg-clip-text text-transparent">
            <span role="img" aria-label="search">🔍</span> DeskSearch
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-lg">
            Search your files by meaning, not just keywords
          </p>
        </div>
      )}
      <div className="relative group">
        <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
          <svg
            className="h-5 w-5 text-gray-400 group-focus-within:text-accent-blue transition-colors"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
            />
          </svg>
        </div>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search your files..."
          className={`w-full bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
            rounded-xl pl-12 pr-4 text-gray-900 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-accent-blue/50 focus:border-accent-blue
            transition-all ${centered ? 'py-4 text-lg' : 'py-3 text-base'}`}
        />
        <div className="absolute inset-y-0 right-0 pr-4 flex items-center gap-2">
          {!query && (
            <kbd className="hidden sm:inline-block text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-dark-border px-1.5 py-0.5 rounded font-mono">
              /
            </kbd>
          )}
          {query && (
            <button
              onClick={() => onQueryChange('')}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
