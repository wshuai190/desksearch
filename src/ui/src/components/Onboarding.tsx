import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';

interface DetectedFolder {
  path: string;
  name: string;
  category: 'documents' | 'developer' | 'notes';
}

type Step = 'welcome' | 'folders' | 'indexing' | 'done';

const CATEGORY_INFO: Record<string, { label: string; icon: string; description: string }> = {
  documents: { label: 'Documents',    icon: '📁', description: 'Your main document storage' },
  developer: { label: 'Code & Projects', icon: '💻', description: 'Source code and project files' },
  notes:     { label: 'Notes',        icon: '📝', description: 'Notes and writing' },
};

const FEATURES = [
  {
    icon: '💬',
    title: 'Search like you\'re talking to someone',
    body: 'Ask "what were the key takeaways from the Q3 meeting?" instead of guessing filenames.',
  },
  {
    icon: '🔒',
    title: 'Completely private — nothing leaves your Mac',
    body: 'All processing happens on your computer. No cloud, no uploads, no data sharing.',
  },
  {
    icon: '⚡',
    title: 'Works on PDFs, Word docs, code, and more',
    body: 'DeskSearch reads and understands dozens of file formats.',
  },
];

export default function Onboarding({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState<Step>('welcome');
  const [folders, setFolders] = useState<DetectedFolder[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [indexingStarted, setIndexingStarted] = useState(false);
  const [fileCount, setFileCount] = useState(0);

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
              Welcome to DeskSearch
            </h1>
            <p className="text-lg text-gray-500 dark:text-gray-400 leading-relaxed">
              Find anything on your computer — by describing what you're looking for, not just the filename.
            </p>
          </div>

          {/* Feature cards */}
          <div className="space-y-3 text-left">
            {FEATURES.map((f, i) => (
              <div key={i} className="flex items-start gap-4 p-4 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-2xl">
                <span className="text-2xl flex-shrink-0">{f.icon}</span>
                <div>
                  <div className="font-semibold text-gray-800 dark:text-gray-200 text-sm">{f.title}</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{f.body}</div>
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
              Get started →
            </button>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Takes about 2 minutes to set up
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
                Which folders should DeskSearch know about?
              </h2>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 pl-11">
              We found these folders on your Mac. Check the ones you'd like to be able to search.
              You can always add or remove folders later.
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
            <div className="text-center py-10 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-2xl">
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                No common folders detected. You can add folders manually after setup.
              </p>
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
                      {cat.description}
                    </span>
                  </label>
                );
              })}
            </div>
          )}

          {/* Select all / none */}
          {folders.length > 1 && (
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <button
                onClick={() => setSelected(new Set(folders.map(f => f.path)))}
                className="tap-sm hover:text-accent-blue transition-colors"
              >
                Select all
              </button>
              <span className="text-gray-300 dark:text-gray-600">·</span>
              <button
                onClick={() => setSelected(new Set())}
                className="tap-sm hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
              >
                Clear selection
              </button>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between pt-2">
            <button
              onClick={() => setStep('welcome')}
              className="tap-sm px-4 py-2.5 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              ← Back
            </button>
            <button
              onClick={handleStartIndexing}
              disabled={selected.size === 0}
              className="tap-sm flex items-center gap-2 px-8 py-3 bg-accent-blue text-white rounded-2xl font-semibold hover:bg-accent-blue-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-accent-blue/25"
            >
              {selected.size === 0
                ? 'Select at least one folder'
                : `Start indexing ${selected.size} folder${selected.size !== 1 ? 's' : ''} →`}
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
              Reading your files…
            </h2>
            <p className="text-gray-500 dark:text-gray-400 text-sm sm:text-base leading-relaxed">
              DeskSearch is learning what's in your files so it can answer your questions.
              This usually takes a few minutes.
            </p>
          </div>

          {/* File counter */}
          {fileCount > 0 && (
            <div className="inline-flex items-center gap-3 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border px-5 py-3 rounded-2xl">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{fileCount.toLocaleString()}</span>
              <span className="text-sm text-gray-500">files processed</span>
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
            💡 <strong>Tip:</strong> You don't have to wait here — you can start searching as files are indexed.
            Searches will get better as more files are processed.
          </div>

          {fileCount > 0 && (
            <button
              onClick={onComplete}
              className="tap-sm text-sm text-accent-blue hover:text-accent-blue-hover underline underline-offset-2 transition-colors"
            >
              I'll start searching now →
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
            You're all set!
          </h2>
          <p className="text-gray-500 dark:text-gray-400 leading-relaxed">
            <strong className="text-gray-700 dark:text-gray-300">{fileCount.toLocaleString()} files</strong> are now
            searchable. Just describe what you're looking for in plain English.
          </p>
        </div>

        {/* Example searches */}
        <div className="text-left bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-2xl p-4 space-y-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
            Try searching for…
          </p>
          {[
            'meeting notes from last week',
            'project budget spreadsheet',
            'notes about the client proposal',
          ].map(q => (
            <div key={q} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <svg className="w-4 h-4 text-accent-blue flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <span className="italic">{q}</span>
            </div>
          ))}
        </div>

        <button
          onClick={onComplete}
          className="tap-sm w-full py-4 bg-accent-blue text-white rounded-2xl font-semibold text-lg hover:bg-accent-blue-hover transition-colors shadow-lg shadow-accent-blue/25"
        >
          Start searching →
        </button>
      </div>
    </div>
  );
}
