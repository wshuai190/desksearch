import { useState, useEffect, useRef } from 'react';
import SearchBar from './components/SearchBar';
import ResultsList from './components/ResultsList';
import Filters from './components/Filters';
import StatusBar from './components/StatusBar';
import IndexingProgress from './components/IndexingProgress';
import Onboarding from './components/Onboarding';
import Dashboard from './components/Dashboard';
import FolderManager from './components/FolderManager';
import FileExplorer from './components/FileExplorer';
import Settings from './components/Settings';
import { useSearch } from './hooks/useSearch';
import { useIndexStatus } from './hooks/useIndexStatus';
import { API_BASE_URL } from './config';
import type { SearchFilters, TabId } from './types';
import type { SearchBarHandle } from './components/SearchBar';

const DEFAULT_FILTERS: SearchFilters = {
  file_types: [],
  date_from: '',
  date_to: '',
  folder: '',
};

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'search',    label: 'Search',    icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z' },
  { id: 'dashboard', label: 'Dashboard', icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z' },
  { id: 'files',     label: 'Files',     icon: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z' },
  { id: 'folders',   label: 'Folders',   icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' },
  { id: 'settings',  label: 'Settings',  icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('search');
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);
  const [darkMode, setDarkMode] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  const [focusFirstResult, setFocusFirstResult] = useState(false);

  const searchBarRef = useRef<SearchBarHandle>(null);
  const { data, loading, error } = useSearch(query, filters);
  const { status, error: statusError } = useIndexStatus();

  const hasQuery = query.trim().length > 0;

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  // Check if onboarding is needed
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/onboarding/status`)
      .then(r => r.json())
      .then(data => setNeedsSetup(data.needs_setup ?? false))
      .catch(() => setNeedsSetup(false));
  }, []);

  // Show nothing while checking
  if (needsSetup === null) {
    return <div className="min-h-screen bg-white dark:bg-dark-bg" />;
  }

  const ThemeToggle = () => (
    <button
      onClick={() => setDarkMode(!darkMode)}
      className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
      title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label="Toggle theme"
    >
      {darkMode ? (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ) : (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      )}
    </button>
  );

  // Show onboarding if needed
  if (needsSetup) {
    return (
      <div className="min-h-screen flex flex-col">
        <header className="flex items-center justify-end px-4 py-3 border-b border-gray-100 dark:border-dark-border">
          <ThemeToggle />
        </header>
        <Onboarding onComplete={() => setNeedsSetup(false)} />
      </div>
    );
  }

  const activeFilterCount =
    filters.file_types.length +
    (filters.date_from ? 1 : 0) +
    (filters.date_to ? 1 : 0) +
    (filters.folder ? 1 : 0);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-dark-border sticky top-0 z-10 bg-white/90 dark:bg-dark-bg/90 backdrop-blur">
        <div className="flex items-center gap-4">
          <span
            className="text-lg font-semibold bg-gradient-to-r from-accent-blue to-blue-400 bg-clip-text text-transparent cursor-pointer select-none"
            onClick={() => { setActiveTab('search'); searchBarRef.current?.focus(); }}
            title="DeskSearch"
          >
            🔍 DeskSearch
          </span>
          {/* Tab navigation — desktop */}
          <nav className="hidden sm:flex items-center gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                  activeTab === tab.id
                    ? 'bg-accent-blue/10 text-accent-blue font-medium'
                    : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover'
                }`}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
                </svg>
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          {activeTab === 'search' && hasQuery && (
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`relative p-2 rounded-lg transition-colors ${
                showFilters || activeFilterCount > 0
                  ? 'bg-accent-blue/10 text-accent-blue'
                  : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover'
              }`}
              title="Toggle filters"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
              </svg>
              {activeFilterCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-accent-blue text-white text-[10px] rounded-full flex items-center justify-center font-medium">
                  {activeFilterCount}
                </span>
              )}
            </button>
          )}
          <ThemeToggle />
        </div>
      </header>

      {/* Mobile tab bar */}
      <nav className="sm:hidden flex border-b border-gray-100 dark:border-dark-border overflow-x-auto bg-white dark:bg-dark-bg">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 min-w-0 flex flex-col items-center gap-0.5 px-2 py-2 text-[10px] transition-colors ${
              activeTab === tab.id
                ? 'text-accent-blue border-b-2 border-accent-blue'
                : 'text-gray-500'
            }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
            </svg>
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Main Content */}
      <main className="flex-1 flex flex-col">
        {activeTab === 'search' && (
          <>
            {!hasQuery && (
              <div className="flex-1 flex items-center justify-center px-4">
                <SearchBar
                  ref={searchBarRef}
                  query={query}
                  onQueryChange={setQuery}
                  centered
                  onArrowDown={() => setFocusFirstResult(true)}
                />
              </div>
            )}

            {hasQuery && (
              <div className="flex-1 flex flex-col">
                <div className="px-4 py-4 flex justify-center">
                  <SearchBar
                    ref={searchBarRef}
                    query={query}
                    onQueryChange={setQuery}
                    centered={false}
                    onArrowDown={() => setFocusFirstResult(true)}
                  />
                </div>

                <IndexingProgress isIndexing={status?.is_indexing ?? false} />

                <div className="flex-1 px-4 pb-16">
                  <div className="max-w-3xl mx-auto flex gap-6">
                    <Filters
                      filters={filters}
                      onFiltersChange={setFilters}
                      visible={showFilters}
                    />
                    <div className="flex-1 min-w-0">
                      <ResultsList
                        data={data}
                        loading={loading}
                        error={error}
                        query={query}
                        focusFirstResult={focusFirstResult}
                        onFocusFirstResultConsumed={() => setFocusFirstResult(false)}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'files' && <FileExplorer />}
        {activeTab === 'folders' && <FolderManager />}
        {activeTab === 'settings' && <Settings />}
      </main>

      <StatusBar status={status} error={statusError} />
    </div>
  );
}
