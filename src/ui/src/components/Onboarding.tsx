import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { useI18n } from '../i18n';

interface DetectedFolder {
  path: string;
  name: string;
  category: 'documents' | 'developer' | 'notes';
}

type Step = 'welcome' | 'folders' | 'indexing' | 'done';

// Labels/descriptions are i18n keys — the `onboarding.` prefix lives in the key
// itself, so these can be passed straight to `t(...)` at render time.
const CATEGORY_INFO: Record<string, { labelKey: string; icon: string; descriptionKey: string }> = {
  documents: { labelKey: 'onboarding.category.documents.label', icon: '📁', descriptionKey: 'onboarding.category.documents.description' },
  developer: { labelKey: 'onboarding.category.developer.label', icon: '💻', descriptionKey: 'onboarding.category.developer.description' },
  notes:     { labelKey: 'onboarding.category.notes.label',     icon: '📝', descriptionKey: 'onboarding.category.notes.description' },
};

const FEATURES = [
  {
    icon: '💬',
    titleKey: 'onboarding.features.conversational.title',
    bodyKey: 'onboarding.features.conversational.body',
  },
  {
    icon: '🔒',
    titleKey: 'onboarding.features.private.title',
    bodyKey: 'onboarding.features.private.body',
  },
  {
    icon: '⚡',
    titleKey: 'onboarding.features.formats.title',
    bodyKey: 'onboarding.features.formats.body',
  },
];

const EXAMPLE_QUERY_KEYS = [
  'onboarding.done.example.meeting',
  'onboarding.done.example.budget',
  'onboarding.done.example.proposal',
];

export default function Onboarding({ onComplete }: { onComplete: () => void }) {
  const { t, formatNumber } = useI18n();
  const [step, setStep] = useState<Step>('welcome');
  const [folders, setFolders] = useState<DetectedFolder[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [indexingStarted, setIndexingStarted] = useState(false);
  const [fileCount, setFileCount] = useState(0);
  const [manualPath, setManualPath] = useState('');

  // Detect folders when entering the folders step
  useEffect(() => {
    if (step !== 'folders') return;
    setLoading(true);
    fetch(`${API_BASE_URL}/api/onboarding/detect-folders`)
      .then(r => r.json())
      .then(data => {
        const f: DetectedFolder[] = data.folders || [];
        setFolders(f);
        setSelected(new Set(f.map(x => x.path))); // select all by default
      })
      .catch(() => setFolders([]))
      .finally(() => setLoading(false));
  }, [step]);

  // Poll status while indexing
  useEffect(() => {
    if (step !== 'indexing' || !indexingStarted) return;
    const interval = setInterval(() => {
      fetch(`${API_BASE_URL}/api/status`)
        .then(r => r.json())
        .then(data => {
          setFileCount(data.total_documents || 0);
          if (!data.is_indexing && data.total_documents > 0) {
            clearInterval(interval);
            setStep('done');
          }
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(interval);
  }, [step, indexingStarted]);

  const toggleFolder = useCallback((path: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const addManualFolder = useCallback(() => {
    const trimmed = manualPath.trim();
    if (!trimmed) return;
    // Add to folders list if not already there
    if (!folders.some(f => f.path === trimmed)) {
      const name = trimmed.split('/').filter(Boolean).pop() || trimmed;
      setFolders(prev => [...prev, { path: trimmed, name, category: 'documents' }]);
    }
    setSelected(prev => new Set(prev).add(trimmed));
    setManualPath('');
  }, [manualPath, folders]);

  const handleStartIndexing = async () => {
    if (selected.size === 0) return;
    setStep('indexing');
    try {
      const res = await fetch(`${API_BASE_URL}/api/onboarding/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: Array.from(selected), start_indexing: true }),
      });
      if (res.ok) setIndexingStarted(true);
    } catch {
      // Still show indexing step even if request failed
    }
  };

  // ── Step: Welcome ──────────────────────────────────────────────────────────
  if (step === 'welcome') {
    return (
      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <div className="max-w-lg w-full space-y-8 text-center">
          {/* Logo & title */}
          <div className="space-y-3">
            <div className="text-6xl">🔍</div>
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white">
              {t('onboarding.welcome.title')}
            </h1>
            <p className="text-lg text-gray-500 dark:text-gray-400 leading-relaxed">
              {t('onboarding.welcome.subtitle')}
            </p>
          </div>

          {/* Feature cards */}
          <div className="space-y-3 text-left">
            {FEATURES.map((f, i) => (
              <div key={i} className="flex items-start gap-4 p-4 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-2xl">
                <span className="text-2xl flex-shrink-0">{f.icon}</span>
                <div>
                  <div className="font-semibold text-gray-800 dark:text-gray-200 text-sm">{t(f.titleKey)}</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{t(f.bodyKey)}</div>
                </div>
              </div>
            ))}
          </div>

          {/* CTA */}
          <div className="space-y-3">
            <button
              onClick={() => setStep('folders')}
              className="tap-sm w-full sm:w-auto px-10 py-4 bg-accent-blue text-white rounded-2xl font-semibold text-lg hover:bg-accent-blue-hover transition-colors shadow-lg shadow-accent-blue/25"
            >
              {t('onboarding.welcome.cta')}
            </button>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              {t('onboarding.welcome.hint')}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ── Step: Select Folders ───────────────────────────────────────────────────
  if (step === 'folders') {
    return (
      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <div className="max-w-lg w-full space-y-6">
          {/* Header */}
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-accent-blue/10 flex items-center justify-center">
                <span className="text-accent-blue text-sm font-bold">1</span>
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
                {t('onboarding.folders.title')}
              </h2>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 pl-11">
              {t('onboarding.folders.subtitle')}
            </p>
          </div>

          {/* Folder list */}
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-16 bg-gray-100 dark:bg-dark-border rounded-2xl animate-pulse" />
              ))}
            </div>
          ) : folders.length === 0 ? (
            <div className="space-y-4">
              <div className="text-center py-6 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-2xl">
                <p className="text-gray-500 dark:text-gray-400 text-sm">
                  {t('onboarding.folders.empty')}
                </p>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={manualPath}
                  onChange={e => setManualPath(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addManualFolder()}
                  placeholder={t('onboarding.folders.pathPlaceholder')}
                  className="flex-1 px-4 py-3 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-blue"
                />
                <button
                  onClick={addManualFolder}
                  disabled={!manualPath.trim()}
                  className="tap-sm px-5 py-3 bg-accent-blue text-white rounded-xl font-medium text-sm hover:bg-accent-blue-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {t('common.add')}
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {folders.map(f => {
                const cat = CATEGORY_INFO[f.category] || CATEGORY_INFO.documents;
                const isSelected = selected.has(f.path);
                return (
                  <label
                    key={f.path}
                    className={`flex items-center gap-4 p-4 rounded-2xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-accent-blue bg-accent-blue/5 dark:bg-accent-blue/10'
                        : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-gray-600 bg-white dark:bg-dark-surface'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleFolder(f.path)}
                      className="w-5 h-5 rounded-lg border-gray-300 text-accent-blue focus:ring-accent-blue flex-shrink-0"
                    />
                    <span className="text-2xl flex-shrink-0">{cat.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-gray-800 dark:text-white text-sm">{f.name}</div>
                      <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate" title={f.path}>
                        {f.path.replace(/^\/Users\/[^/]+/, '~')}
                      </div>
                    </div>
                    <span className="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0 hidden sm:block">
                      {t(cat.descriptionKey)}
                    </span>
                  </label>
                );
              })}
            </div>
          )}

          {/* Add folder manually */}
          {folders.length > 0 && (
            <div className="flex gap-2">
              <input
                type="text"
                value={manualPath}
                onChange={e => setManualPath(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addManualFolder()}
                placeholder={t('onboarding.folders.addAnotherPlaceholder')}
                className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-blue"
              />
              <button
                onClick={addManualFolder}
                disabled={!manualPath.trim()}
                className="tap-sm px-4 py-2.5 bg-accent-blue text-white rounded-xl font-medium text-sm hover:bg-accent-blue-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t('common.add')}
              </button>
            </div>
          )}

          {/* Select all / none */}
          {folders.length > 1 && (
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <button
                onClick={() => setSelected(new Set(folders.map(f => f.path)))}
                className="tap-sm hover:text-accent-blue transition-colors"
              >
                {t('common.selectAll')}
              </button>
              <span className="text-gray-300 dark:text-gray-600">·</span>
              <button
                onClick={() => setSelected(new Set())}
                className="tap-sm hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
              >
                {t('onboarding.folders.clearSelection')}
              </button>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between pt-2">
            <button
              onClick={() => setStep('welcome')}
              className="tap-sm px-4 py-2.5 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              ← {t('common.back')}
            </button>
            <button
              onClick={handleStartIndexing}
              disabled={selected.size === 0}
              className="tap-sm flex items-center gap-2 px-8 py-3 bg-accent-blue text-white rounded-2xl font-semibold hover:bg-accent-blue-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-accent-blue/25"
            >
              {selected.size === 0
                ? t('onboarding.folders.selectAtLeastOne')
                : t('onboarding.folders.startIndexing', { count: selected.size })}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Step: Indexing ─────────────────────────────────────────────────────────
  if (step === 'indexing') {
    return (
      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <div className="max-w-md w-full text-center space-y-7">
          {/* Animated icon */}
          <div className="flex justify-center">
            <div className="relative">
              <div className="w-24 h-24 rounded-3xl bg-accent-blue/10 flex items-center justify-center">
                <span className="text-5xl">📚</span>
              </div>
              <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-900/40 border-2 border-white dark:border-dark-bg flex items-center justify-center">
                <svg className="w-4 h-4 text-amber-500 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              {t('onboarding.indexing.title')}
            </h2>
            <p className="text-gray-500 dark:text-gray-400 text-sm sm:text-base leading-relaxed">
              {t('onboarding.indexing.body')}
            </p>
          </div>

          {/* File counter */}
          {fileCount > 0 && (
            <div className="inline-flex items-center gap-3 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border px-5 py-3 rounded-2xl">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{formatNumber(fileCount)}</span>
              <span className="text-sm text-gray-500">{t('onboarding.indexing.filesProcessed')}</span>
            </div>
          )}

          {/* Progress bar (indeterminate) */}
          <div className="w-full bg-gray-200 dark:bg-dark-border rounded-full h-2 overflow-hidden">
            <div
              className="h-full bg-accent-blue rounded-full animate-pulse"
              style={{ width: fileCount > 0 ? `${Math.min(90, fileCount / 10)}%` : '15%', transition: 'width 1s ease-out' }}
            />
          </div>

          <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/40 rounded-2xl p-4 text-sm text-blue-700 dark:text-blue-300">
            💡 <strong>{t('onboarding.indexing.tipLabel')}</strong> {t('onboarding.indexing.tipBody')}
          </div>

          {fileCount > 0 && (
            <button
              onClick={onComplete}
              className="tap-sm text-sm text-accent-blue hover:text-accent-blue-hover underline underline-offset-2 transition-colors"
            >
              {t('onboarding.indexing.startSearching')}
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Step: Done ─────────────────────────────────────────────────────────────
  return (
    <div className="flex-1 flex items-center justify-center px-4 py-8">
      <div className="max-w-md w-full text-center space-y-7">
        <div className="flex justify-center">
          <div className="w-24 h-24 rounded-3xl bg-green-100 dark:bg-green-950/40 flex items-center justify-center">
            <span className="text-5xl">🎉</span>
          </div>
        </div>

        <div className="space-y-2">
          <h2 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">
            {t('onboarding.done.title')}
          </h2>
          <p className="text-gray-500 dark:text-gray-400 leading-relaxed">
            <strong className="text-gray-700 dark:text-gray-300">
              {t('onboarding.done.count', { count: fileCount, files: formatNumber(fileCount) })}
            </strong>{' '}
            {t('onboarding.done.bodyRest')}
          </p>
        </div>

        {/* Example searches */}
        <div className="text-left bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-2xl p-4 space-y-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
            {t('onboarding.done.trySearching')}
          </p>
          {EXAMPLE_QUERY_KEYS.map(q => (
            <div key={q} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <svg className="w-4 h-4 text-accent-blue flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <span className="italic">{t(q)}</span>
            </div>
          ))}
        </div>

        <button
          onClick={onComplete}
          className="tap-sm w-full py-4 bg-accent-blue text-white rounded-2xl font-semibold text-lg hover:bg-accent-blue-hover transition-colors shadow-lg shadow-accent-blue/25"
        >
          {t('onboarding.done.startSearching')}
        </button>
      </div>
    </div>
  );
}
