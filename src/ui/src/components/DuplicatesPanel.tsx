import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { DuplicatesResponse, DuplicatePair } from '../types';

function SimilarityBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.98 ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800/40'
    : score >= 0.95 ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 border-orange-200 dark:border-orange-800/40'
    : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800/40';

  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${color}`}>
      {pct}% similar
    </span>
  );
}

function FileCard({ filename, path, onOpen }: {
  filename: string;
  path: string;
  onOpen: () => void;
}) {
  const shortPath = path.replace(/^\/Users\/[^/]+/, '~');
  return (
    <div className="flex-1 min-w-0 p-3 bg-gray-50 dark:bg-dark-hover rounded-lg border border-gray-100 dark:border-dark-border">
      <div className="flex items-start gap-2">
        <span className="text-lg flex-shrink-0 mt-0.5">📄</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
            {filename}
          </div>
          <div className="text-[11px] text-gray-400 truncate mt-0.5" title={path}>
            {shortPath}
          </div>
        </div>
      </div>
      <div className="mt-2.5 flex gap-2">
        <button
          onClick={onOpen}
          className="flex-1 text-xs py-1.5 px-2 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-md hover:border-accent-blue/50 hover:text-accent-blue transition-colors text-center text-gray-600 dark:text-gray-300 font-medium"
        >
          Open
        </button>
        <button
          onClick={async () => navigator.clipboard.writeText(path)}
          className="text-xs py-1.5 px-2 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-md hover:border-gray-300 transition-colors text-gray-400"
          title="Copy path"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        </button>
      </div>
    </div>
  );
}

function DuplicateRow({ pair, onOpen }: { pair: DuplicatePair; onOpen: (path: string) => void }) {
  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <SimilarityBadge score={pair.similarity} />
        <span className="text-xs text-gray-400">
          {pair.similarity >= 0.98
            ? '⚠️ Near-identical content'
            : pair.similarity >= 0.95
            ? 'Very similar content'
            : 'Similar content'}
        </span>
      </div>
      <div className="flex gap-3 items-stretch">
        <FileCard
          filename={pair.filename_a}
          path={pair.path_a}
          onOpen={() => onOpen(pair.path_a)}
        />
        <div className="flex-shrink-0 self-center">
          <div className="w-6 h-6 rounded-full bg-gray-100 dark:bg-dark-border flex items-center justify-center">
            <svg className="w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
            </svg>
          </div>
        </div>
        <FileCard
          filename={pair.filename_b}
          path={pair.path_b}
          onOpen={() => onOpen(pair.path_b)}
        />
      </div>
    </div>
  );
}

export default function DuplicatesPanel() {
  const [data, setData] = useState<DuplicatesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0.92);

  const load = (t: number) => {
    setLoading(true);
    setError(null);
    fetch(`${API_BASE_URL}/api/duplicates?threshold=${t}`)
      .then(r => { if (!r.ok) throw new Error('Failed to detect duplicates'); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(threshold); }, []);

  const openFile = (path: string) => {
    fetch(`${API_BASE_URL}/api/open/${encodeURIComponent(path)}`);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            🔁 Duplicate Files
          </h2>
          <p className="text-sm text-gray-400 mt-0.5">
            Files with nearly identical content
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Sensitivity:</label>
          <select
            value={threshold}
            onChange={e => {
              const t = Number(e.target.value);
              setThreshold(t);
              load(t);
            }}
            className="text-sm border border-gray-200 dark:border-dark-border rounded-lg px-2 py-1.5 bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-blue/50"
          >
            <option value={0.98}>Very strict (98%+)</option>
            <option value={0.95}>Strict (95%+)</option>
            <option value={0.92}>Normal (92%+)</option>
            <option value={0.85}>Loose (85%+)</option>
          </select>
          <button
            onClick={() => load(threshold)}
            className="p-1.5 rounded-lg border border-gray-200 dark:border-dark-border text-gray-500 hover:text-accent-blue hover:border-accent-blue/50 transition-colors"
            title="Re-scan"
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {loading && (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-36 bg-gray-100 dark:bg-dark-border rounded-xl" />
          ))}
        </div>
      )}

      {error && !loading && (
        <div className="text-center py-12">
          <div className="text-3xl mb-3">⚠️</div>
          <p className="text-gray-500">Scan failed</p>
          <p className="text-xs text-gray-400 mt-1">{error}</p>
          <button onClick={() => load(threshold)} className="mt-3 text-sm text-accent-blue hover:underline">
            Try again
          </button>
        </div>
      )}

      {!loading && !error && data && (
        <>
          {/* Summary banner */}
          {data.total > 0 ? (
            <div className="mb-5 flex items-center gap-3 p-4 rounded-xl bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800/30">
              <span className="text-2xl">⚠️</span>
              <div>
                <p className="text-sm font-semibold text-orange-700 dark:text-orange-300">
                  Found {data.total} {data.total === 1 ? 'pair' : 'pairs'} of similar files
                </p>
                <p className="text-xs text-orange-600/70 dark:text-orange-400/70 mt-0.5">
                  Review them below and delete any unwanted copies
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-16 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl">
              <div className="text-4xl mb-3">✅</div>
              <p className="text-gray-700 dark:text-gray-300 font-semibold">No duplicates found</p>
              <p className="text-sm text-gray-400 mt-1">
                All your files have unique content at the {Math.round(threshold * 100)}% similarity threshold
              </p>
            </div>
          )}

          {/* Duplicate pairs */}
          <div className="space-y-3">
            {data.pairs.map(pair => (
              <DuplicateRow
                key={`${pair.doc_id_a}-${pair.doc_id_b}`}
                pair={pair}
                onOpen={openFile}
              />
            ))}
          </div>

          {data.total > 0 && (
            <p className="text-xs text-gray-400 text-center mt-6">
              Similarity is based on document content, not filenames.
              <br />Open both files to compare before deleting.
            </p>
          )}
        </>
      )}
    </div>
  );
}
