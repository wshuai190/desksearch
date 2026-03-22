import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';

interface DetectedFolder {
  path: string;
  name: string;
  category: 'documents' | 'developer' | 'notes';
}

type Step = 'welcome' | 'folders' | 'indexing' | 'done';

const CATEGORY_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  documents: { label: 'Documents', color: 'text-green-400', icon: '📁' },
  developer: { label: 'Developer', color: 'text-blue-400', icon: '💻' },
  notes:     { label: 'Notes',     color: 'text-purple-400', icon: '📝' },
};

export default function Onboarding({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState<Step>('welcome');
  const [folders, setFolders] = useState<DetectedFolder[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [indexingStarted, setIndexingStarted] = useState(false);
  const [pollCount, setPollCount] = useState(0);

  // Detect folders when entering the folders step
  useEffect(() => {
    if (step !== 'folders') return;
    setLoading(true);
    fetch(`${API_BASE_URL}/api/onboarding/detect-folders`)
      .then(r => r.json())
      .then(data => {
        const f: DetectedFolder[] = data.folders || [];
        setFolders(f);
        // Select all by default
        setSelected(new Set(f.map(x => x.path)));
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
          setPollCount(data.total_documents || 0);
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
      if (res.ok) {
        setIndexingStarted(true);
      }
    } catch {
      // If the request fails, still show indexing step
    }
  };

  // -- Step: Welcome --
  if (step === 'welcome') {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <div className="max-w-lg text-center space-y-8">
          <div className="space-y-3">
            <h1 className="text-4xl font-bold bg-gradient-to-r from-accent-blue to-blue-400 bg-clip-text text-transparent">
              Welcome to DeskSearch
            </h1>
            <p className="text-lg text-gray-500 dark:text-gray-400">
              Private semantic search for your local files.
              Everything runs on your machine — nothing leaves it.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-4 text-sm text-gray-500 dark:text-gray-400">
            <div className="p-4 rounded-xl bg-gray-50 dark:bg-dark-card border border-gray-100 dark:border-dark-border">
              <div className="text-2xl mb-2">🔍</div>
              <div className="font-medium text-gray-700 dark:text-gray-300">Smart Search</div>
              <div className="mt-1">Understands meaning, not just keywords</div>
            </div>
            <div className="p-4 rounded-xl bg-gray-50 dark:bg-dark-card border border-gray-100 dark:border-dark-border">
              <div className="text-2xl mb-2">🔒</div>
              <div className="font-medium text-gray-700 dark:text-gray-300">100% Private</div>
              <div className="mt-1">All processing happens locally</div>
            </div>
            <div className="p-4 rounded-xl bg-gray-50 dark:bg-dark-card border border-gray-100 dark:border-dark-border">
              <div className="text-2xl mb-2">📄</div>
              <div className="font-medium text-gray-700 dark:text-gray-300">Multi-Format</div>
              <div className="mt-1">PDF, DOCX, code, notes, and more</div>
            </div>
          </div>

          <button
            onClick={() => setStep('folders')}
            className="px-8 py-3 bg-accent-blue text-white rounded-xl font-medium
              hover:bg-blue-600 transition-colors text-lg"
          >
            Get Started
          </button>
        </div>
      </div>
    );
  }

  // -- Step: Select Folders --
  if (step === 'folders') {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <div className="max-w-lg w-full space-y-6">
          <div className="text-center space-y-2">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              Choose folders to index
            </h2>
            <p className="text-gray-500 dark:text-gray-400">
              We found these folders on your system. Select which ones to search.
            </p>
          </div>

          {loading ? (
            <div className="text-center py-8 text-gray-400">Scanning folders...</div>
          ) : folders.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              No common folders detected. You can add folders later.
            </div>
          ) : (
            <div className="space-y-2">
              {folders.map(f => {
                const cat = CATEGORY_LABELS[f.category] || CATEGORY_LABELS.documents;
                const isSelected = selected.has(f.path);
                return (
                  <label
                    key={f.path}
                    className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                      isSelected
                        ? 'border-accent-blue bg-accent-blue/5 dark:bg-accent-blue/10'
                        : 'border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-gray-600'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleFolder(f.path)}
                      className="w-4 h-4 rounded border-gray-300 text-accent-blue focus:ring-accent-blue"
                    />
                    <span className="text-lg">{cat.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-gray-900 dark:text-white">{f.name}</div>
                      <div className="text-sm text-gray-400 truncate">{f.path}</div>
                    </div>
                    <span className={`text-xs font-medium ${cat.color}`}>{cat.label}</span>
                  </label>
                );
              })}
            </div>
          )}

          <div className="flex justify-between pt-2">
            <button
              onClick={() => setStep('welcome')}
              className="px-6 py-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              Back
            </button>
            <button
              onClick={handleStartIndexing}
              disabled={selected.size === 0}
              className="px-8 py-3 bg-accent-blue text-white rounded-xl font-medium
                hover:bg-blue-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Start Indexing ({selected.size} folder{selected.size !== 1 ? 's' : ''})
            </button>
          </div>
        </div>
      </div>
    );
  }

  // -- Step: Indexing --
  if (step === 'indexing') {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center space-y-6">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              Indexing your files
            </h2>
            <p className="text-gray-500 dark:text-gray-400">
              This may take a few minutes depending on the number of files.
            </p>
          </div>

          {/* Animated spinner */}
          <div className="flex justify-center">
            <div className="w-16 h-16 border-4 border-gray-200 dark:border-dark-border border-t-accent-blue rounded-full animate-spin" />
          </div>

          <div className="space-y-2">
            <div className="text-3xl font-bold text-accent-blue">{pollCount}</div>
            <div className="text-sm text-gray-400">files indexed so far</div>
          </div>

          <div className="w-full bg-gray-200 dark:bg-dark-border rounded-full h-1.5 overflow-hidden">
            <div
              className="h-full bg-accent-blue rounded-full transition-all duration-500"
              style={{ width: pollCount > 0 ? `${Math.min(95, pollCount)}%` : '5%' }}
            />
          </div>
        </div>
      </div>
    );
  }

  // -- Step: Done --
  return (
    <div className="flex-1 flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="text-5xl">✅</div>
        <div className="space-y-2">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            You're all set!
          </h2>
          <p className="text-gray-500 dark:text-gray-400">
            {pollCount} files have been indexed and are ready to search.
          </p>
        </div>

        <button
          onClick={onComplete}
          className="px-8 py-3 bg-accent-blue text-white rounded-xl font-medium
            hover:bg-blue-600 transition-colors text-lg"
        >
          Start Searching
        </button>
      </div>
    </div>
  );
}
