import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { CollectionsResponse, TopicInfo } from '../types';

const TOPIC_COLORS = [
  'bg-blue-100 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800/40 text-blue-700 dark:text-blue-300',
  'bg-purple-100 dark:bg-purple-900/30 border-purple-200 dark:border-purple-800/40 text-purple-700 dark:text-purple-300',
  'bg-green-100 dark:bg-green-900/30 border-green-200 dark:border-green-800/40 text-green-700 dark:text-green-300',
  'bg-orange-100 dark:bg-orange-900/30 border-orange-200 dark:border-orange-800/40 text-orange-700 dark:text-orange-300',
  'bg-pink-100 dark:bg-pink-900/30 border-pink-200 dark:border-pink-800/40 text-pink-700 dark:text-pink-300',
  'bg-teal-100 dark:bg-teal-900/30 border-teal-200 dark:border-teal-800/40 text-teal-700 dark:text-teal-300',
  'bg-indigo-100 dark:bg-indigo-900/30 border-indigo-200 dark:border-indigo-800/40 text-indigo-700 dark:text-indigo-300',
  'bg-rose-100 dark:bg-rose-900/30 border-rose-200 dark:border-rose-800/40 text-rose-700 dark:text-rose-300',
];

const DOT_COLORS = [
  'bg-blue-500', 'bg-purple-500', 'bg-green-500', 'bg-orange-500',
  'bg-pink-500', 'bg-teal-500', 'bg-indigo-500', 'bg-rose-500',
];

function TopicCard({ topic, index, onOpenFile }: {
  topic: TopicInfo;
  index: number;
  onOpenFile: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const colorClass = TOPIC_COLORS[index % TOPIC_COLORS.length];
  const dotColor = DOT_COLORS[index % DOT_COLORS.length];
  const shown = expanded ? topic.doc_filenames : topic.doc_filenames.slice(0, 4);
  const remaining = topic.doc_count - 4;

  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl overflow-hidden hover:border-gray-200 dark:hover:border-dark-hover transition-colors">
      {/* Topic header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3.5 text-left"
      >
        <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${dotColor}`} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-gray-800 dark:text-gray-200 truncate">
            {topic.label}
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {topic.doc_count} document{topic.doc_count !== 1 ? 's' : ''}
          </div>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${colorClass}`}>
          {topic.doc_count}
        </span>
        <svg
          className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* File list */}
      {expanded && (
        <div className="border-t border-gray-50 dark:border-dark-border pb-2">
          {shown.map((fname, i) => (
            <button
              key={topic.doc_paths[i]}
              onClick={() => onOpenFile(topic.doc_paths[i])}
              className="w-full flex items-center gap-2.5 px-4 py-2 hover:bg-gray-50 dark:hover:bg-dark-hover text-left transition-colors group"
            >
              <span className="text-sm flex-shrink-0">📄</span>
              <span className="text-sm text-gray-700 dark:text-gray-300 truncate group-hover:text-accent-blue transition-colors">
                {fname}
              </span>
            </button>
          ))}
          {!expanded && remaining > 0 && (
            <button
              onClick={() => setExpanded(true)}
              className="w-full text-center py-2 text-xs text-accent-blue hover:text-blue-700 transition-colors"
            >
              +{remaining} more files
            </button>
          )}
          {expanded && topic.doc_count > 4 && (
            <button
              onClick={() => setExpanded(false)}
              className="w-full text-center py-2 text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              Show less
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function TopicsPanel() {
  const [data, setData] = useState<CollectionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nTopics, setNTopics] = useState<number | undefined>(undefined);

  const load = (n?: number) => {
    setLoading(true);
    setError(null);
    const url = n
      ? `${API_BASE_URL}/api/collections?n_topics=${n}`
      : `${API_BASE_URL}/api/collections`;
    fetch(url)
      .then(r => { if (!r.ok) throw new Error('Failed to load topics'); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(nTopics); }, []);

  const handleNChange = (n: number) => {
    setNTopics(n);
    load(n);
  };

  const openFile = (path: string) => {
    fetch(`${API_BASE_URL}/api/open/${encodeURIComponent(path)}`);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            🗂 Smart Collections
          </h2>
          <p className="text-sm text-gray-400 mt-0.5">
            Your documents, automatically grouped by topic
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Topics:</label>
          <select
            value={nTopics ?? 0}
            onChange={e => handleNChange(Number(e.target.value) || 0)}
            className="text-sm border border-gray-200 dark:border-dark-border rounded-lg px-2 py-1.5 bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-blue/50"
          >
            <option value={0}>Auto</option>
            {[3, 5, 7, 10, 12].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <button
            onClick={() => load(nTopics)}
            className="p-1.5 rounded-lg border border-gray-200 dark:border-dark-border text-gray-500 hover:text-accent-blue hover:border-accent-blue/50 transition-colors"
            title="Refresh clusters"
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {loading && (
        <div className="space-y-3 animate-pulse">
          {[1,2,3,4].map(i => (
            <div key={i} className="h-16 bg-gray-100 dark:bg-dark-border rounded-xl" />
          ))}
        </div>
      )}

      {error && !loading && (
        <div className="text-center py-12">
          <div className="text-3xl mb-3">⚠️</div>
          <p className="text-gray-500">Could not load topics</p>
          <p className="text-xs text-gray-400 mt-1">{error}</p>
          <button
            onClick={() => load(nTopics)}
            className="mt-3 text-sm text-accent-blue hover:underline"
          >
            Try again
          </button>
        </div>
      )}

      {!loading && !error && data && data.topics.length === 0 && (
        <div className="text-center py-16 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl">
          <div className="text-4xl mb-3">🗂</div>
          <p className="text-gray-600 dark:text-gray-400 font-medium">Not enough documents</p>
          <p className="text-sm text-gray-400 mt-1">
            Index at least a few documents to see topic groups
          </p>
        </div>
      )}

      {!loading && data && data.topics.length > 0 && (
        <>
          <div className="mb-4 text-sm text-gray-500 dark:text-gray-400">
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {data.topics.length} topics
            </span>
            {' '}discovered across{' '}
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {data.total_docs_clustered} documents
            </span>
          </div>

          <div className="space-y-2">
            {data.topics.map((topic, i) => (
              <TopicCard
                key={topic.id}
                topic={topic}
                index={i}
                onOpenFile={openFile}
              />
            ))}
          </div>

          <p className="text-xs text-gray-400 text-center mt-6">
            Topics are generated from document content using AI clustering.
            <br />They update automatically as your index changes.
          </p>
        </>
      )}
    </div>
  );
}
