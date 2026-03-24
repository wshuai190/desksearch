import { useState, useEffect, useRef, lazy, Suspense } from 'react';
import SearchBar from './components/SearchBar';
import ResultsList from './components/ResultsList';
import Filters from './components/Filters';
import StatusBar from './components/StatusBar';
import IndexingProgress from './components/IndexingProgress';
import Onboarding from './components/Onboarding';
import { useSearch } from './hooks/useSearch';
import { useIndexStatus } from './hooks/useIndexStatus';
import { API_BASE_URL } from './config';
import type { SearchFilters, TabId } from './types';
import type { SearchBarHandle } from './components/SearchBar';

// Lazy-load heavy tabs to keep initial bundle small
const Dashboard = lazy(() => import('./components/Dashboard'));
const FileExplorer = lazy(() => import('./components/FileExplorer'));
const FolderManager = lazy(() => import('./components/FolderManager'));
const Settings = lazy(() => import('./components/Settings'));
const AnalyticsDashboard = lazy(() => import('./components/AnalyticsDashboard'));
const TopicsPanel = lazy(() => import('./components/TopicsPanel'));
const DuplicatesPanel = lazy(() => import('./components/DuplicatesPanel'));

const DEFAULT_FILTERS: SearchFilters = {
  file_types: [],
  date_from: '',
  date_to: '',
  folder: '',
};

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'search',    label: 'Search',     icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z' },
  { id: 'dashboard', label: 'Dashboard',  icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z' },
  { id: 'files',     label: 'Files',      icon: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z' },
  { id: 'folders',   label: 'Folders',    icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' },
  { id: 'analytics', label: 'Insights',   icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { id: 'topics',    label: 'Topics',     icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10' },
  { id: 'duplicates',label: 'Duplicates', icon: 'M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z' },
  { id: 'settings',  label: 'Settings',   icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
];

// Skeleton fallback for lazy-loaded tabs
function TabSkeleton() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-4">
      <div className="h-6 skeleton rounded-lg w-40" />
      <div className="h-4 skeleton rounded-lg w-full" />
      <div className="h-4 skeleton rounded-lg w-5/6" />
      <div className="h-4 skeleton rounded-lg w-4/6" />
      <div className="grid grid-cols-3 gap-4 mt-6">
        <div className="h-24 skeleton rounded-xl" />
        <div className="h-24 skeleton rounded-xl" />
        <div className="h-24 skeleton rounded-xl" />
      </div>
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('search');
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);
  const [darkMode, setDarkMode] = useState(() => {
    const stored = localStorage.getItem('desksearch:darkMode');
    if (stored !== null) return stored === 'true';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const [showFilters, setShowFilters] = useState(false);
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  const [focusFirstResult, setFocusFirstResult] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const searchBarRef = useRef<SearchBarHandle>(null);
  const { data, loading, error } = useSearch(query, filters);
  const { status, error: statusError } = useIndexStatus();

  const hasQuery = query.trim().length > 0;

  // Apply dark mode class + persist preference
  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
    localStorage.setItem('desksearch:darkMode', String(darkMode));
  }, [darkMode]);

  // Listen for system color scheme changes
  useEffect(() => {
    const stored = localStorage.getItem('desksearch:darkMode');
    if (stored !== null) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setDarkMode(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

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

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    localStorage.setItem('desksearch:darkMode', String(!darkMode));
  };

  // Show onboarding if needed
  if (needsSetup) {
    return (
      <div className="min-h-screen flex flex-col bg-white dark:bg-dark-bg">
        <header className="flex items-center justify-end px-4 py-3 border-b border-gray-100 dark:border-dark-border">
          <ThemeToggleButton darkMode={darkMode} onClick={toggleDarkMode} />
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
    <div className="min-h-screen flex bg-white dark:bg-dark-bg">
      {/* ── Desktop Sidebar ─────────────────────────────────────── */}
      <aside className={`hidden sm:flex flex-col border-r border-gray-100 dark:border-dark-border bg-gray-50/50 dark:bg-dark-surface/50 flex-shrink-0 transition-all duration-200 ${sidebarCollapsed ? 'w-16' : 'w-52'}`}>
        {/* Logo */}
        <div className="h-14 flex items-center gap-2.5 px-4 border-b border-gray-100 dark:border-dark-border flex-shrink-0">
          <div className="w-7 h-7 rounded-lg bg-accent-blue flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          {!sidebarCollapsed && (
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              DeskSearch
            </span>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id === 'search') searchBarRef.current?.focus();
                }}
                className={`nav-item w-full flex items-center gap-2.5 rounded-lg transition-all duration-150 min-h-0 ${
                  sidebarCollapsed ? 'px-0 py-2 justify-center' : 'px-3 py-2'
                } ${
                  isActive
                    ? 'active bg-accent-blue/10 text-accent-blue font-medium'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover'
                }`}
                title={sidebarCollapsed ? tab.label : undefined}
              >
                <svg className={`flex-shrink-0 ${sidebarCollapsed ? 'w-5 h-5' : 'w-4 h-4'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={isActive ? 2.2 : 1.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
                </svg>
                {!sidebarCollapsed && (
                  <span className="text-[13px] truncate">{tab.label}</span>
                )}
                {/* Badge: show indexing dot on dashboard */}
                {tab.id === 'dashboard' && status?.is_indexing && (
                  <span className={`w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0 ${sidebarCollapsed ? 'absolute top-1 right-1' : 'ml-auto'}`} />
                )}
                {/* Badge: file count on files tab */}
                {tab.id === 'files' && status && status.total_documents > 0 && !sidebarCollapsed && (
                  <span className="ml-auto text-[10px] font-medium text-gray-400 dark:text-gray-500 tabular-nums">
                    {status.total_documents > 999 ? `${(status.total_documents / 1000).toFixed(1)}k` : status.total_documents}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Bottom section */}
        <div className="border-t border-gray-100 dark:border-dark-border p-2 space-y-1">
          {/* Collapse toggle */}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className={`w-full flex items-center gap-2.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors min-h-0 ${
              sidebarCollapsed ? 'px-0 py-2 justify-center' : 'px-3 py-2'
            }`}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <svg className={`flex-shrink-0 transition-transform ${sidebarCollapsed ? 'w-5 h-5 rotate-180' : 'w-4 h-4'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
            {!sidebarCollapsed && <span className="text-[13px]">Collapse</span>}
          </button>

          {/* Theme toggle */}
          <button
            onClick={toggleDarkMode}
            className={`w-full flex items-center gap-2.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors min-h-0 ${
              sidebarCollapsed ? 'px-0 py-2 justify-center' : 'px-3 py-2'
            }`}
            title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {darkMode ? (
              <svg className={`flex-shrink-0 ${sidebarCollapsed ? 'w-5 h-5' : 'w-4 h-4'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            ) : (
              <svg className={`flex-shrink-0 ${sidebarCollapsed ? 'w-5 h-5' : 'w-4 h-4'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            )}
            {!sidebarCollapsed && <span className="text-[13px]">{darkMode ? 'Light mode' : 'Dark mode'}</span>}
          </button>
        </div>
      </aside>

      {/* ── Main Content ────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header — only on mobile */}
        <header className="sm:hidden flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-dark-border bg-white/90 dark:bg-dark-bg/90 backdrop-blur sticky top-0 z-10">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-accent-blue flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">DeskSearch</span>
          </div>
          <div className="flex items-center gap-2">
            {activeTab === 'search' && hasQuery && (
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`relative min-h-0 p-2 rounded-lg transition-colors ${
                  showFilters || activeFilterCount > 0
                    ? 'bg-accent-blue/10 text-accent-blue'
                    : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
                }`}
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
            <ThemeToggleButton darkMode={darkMode} onClick={toggleDarkMode} />
          </div>
        </header>

        {/* Desktop top bar — filter toggle + search context */}
        {activeTab === 'search' && hasQuery && (
          <div className="hidden sm:flex items-center justify-between px-6 py-2.5 border-b border-gray-100 dark:border-dark-border bg-white/80 dark:bg-dark-bg/80 backdrop-blur">
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span>Searching for &ldquo;<span className="text-gray-700 dark:text-gray-200 font-medium">{query}</span>&rdquo;</span>
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`relative min-h-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                showFilters || activeFilterCount > 0
                  ? 'bg-accent-blue/10 text-accent-blue'
                  : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover'
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
              </svg>
              Filters
              {activeFilterCount > 0 && (
                <span className="w-5 h-5 bg-accent-blue text-white text-[10px] rounded-full flex items-center justify-center font-medium">
                  {activeFilterCount}
                </span>
              )}
            </button>
          </div>
        )}

        {/* Page content */}
        <main className="flex-1 flex flex-col overflow-y-auto mobile-content-pb">
          {activeTab === 'search' && (
            <>
              {!hasQuery && (
                <div className="flex-1 flex items-center justify-center px-4 py-8">
                  <SearchBar
                    ref={searchBarRef}
                    query={query}
                    onQueryChange={setQuery}
                    centered
                    onArrowDown={() => setFocusFirstResult(true)}
                    fileCount={status?.total_documents}
                    isIndexing={status?.is_indexing}
                    lastIndexed={status?.last_indexed}
                    indexSizeMb={status?.index_size_mb}
                  />
                </div>
              )}

              {hasQuery && (
                <div className="flex-1 flex flex-col">
                  <div className="px-4 py-3 sm:py-4 flex justify-center">
                    <SearchBar
                      ref={searchBarRef}
                      query={query}
                      onQueryChange={setQuery}
                      centered={false}
                      onArrowDown={() => setFocusFirstResult(true)}
                    />
                  </div>

                  <IndexingProgress isIndexing={status?.is_indexing ?? false} />

                  <div className="flex-1 px-3 sm:px-6 pb-4">
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

          <Suspense fallback={<TabSkeleton />}>
            {activeTab === 'dashboard' && <Dashboard />}
            {activeTab === 'files' && <FileExplorer />}
            {activeTab === 'folders' && <FolderManager />}
            {activeTab === 'analytics' && <AnalyticsDashboard />}
            {activeTab === 'topics' && <TopicsPanel />}
            {activeTab === 'duplicates' && <DuplicatesPanel />}
            {activeTab === 'settings' && <Settings />}
          </Suspense>
        </main>

        <StatusBar status={status} error={statusError} />
      </div>

      {/* ── Mobile bottom tab bar ───────────────────────────────── */}
      <nav className="sm:hidden fixed bottom-0 left-0 right-0 z-20 flex bg-white/95 dark:bg-dark-bg/95 backdrop-blur border-t border-gray-200 dark:border-dark-border bottom-nav">
        {TABS.slice(0, 5).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex flex-col items-center justify-center gap-0.5 pt-2 pb-1 text-[10px] transition-colors min-h-0 ${
              activeTab === tab.id
                ? 'text-accent-blue'
                : 'text-gray-400 dark:text-gray-500'
            }`}
          >
            <svg
              className={`w-5 h-5 transition-transform ${activeTab === tab.id ? 'scale-110' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={activeTab === tab.id ? 2.5 : 1.8}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
            </svg>
            <span className={activeTab === tab.id ? 'font-semibold' : 'font-medium'}>{tab.label}</span>
          </button>
        ))}
        {/* More menu for remaining tabs */}
        <div className="relative flex-1 flex flex-col items-center justify-center">
          <button
            onClick={() => {
              const el = document.getElementById('mobile-more-menu');
              el?.classList.toggle('hidden');
            }}
            className={`flex flex-col items-center justify-center gap-0.5 pt-2 pb-1 text-[10px] transition-colors min-h-0 ${
              ['topics', 'duplicates', 'settings'].includes(activeTab)
                ? 'text-accent-blue'
                : 'text-gray-400 dark:text-gray-500'
            }`}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
            </svg>
            <span className="font-medium">More</span>
          </button>
          <div id="mobile-more-menu" className="hidden absolute bottom-full right-0 mb-2 w-44 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl shadow-xl overflow-hidden animate-scaleIn z-30">
            {TABS.slice(5).map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  document.getElementById('mobile-more-menu')?.classList.add('hidden');
                }}
                className={`w-full flex items-center gap-2.5 px-4 py-3 text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'bg-accent-blue/10 text-accent-blue font-medium'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-hover'
                }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
                </svg>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>
    </div>
  );
}

// ── Theme toggle button ─────────────────────────────────────────
function ThemeToggleButton({ darkMode, onClick }: { darkMode: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors min-h-0"
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
}
