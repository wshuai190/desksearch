import type { SearchResponse } from '../types';
import ResultCard from './ResultCard';

interface ResultsListProps {
  data: SearchResponse | null;
  loading: boolean;
  error: string | null;
  query: string;
}

export default function ResultsList({ data, loading, error, query }: ResultsListProps) {
  if (!query.trim()) return null;

  if (error) {
    return (
      <div className="text-center py-12">
        <div className="text-red-400 mb-2">
          <svg className="w-8 h-8 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
        </div>
        <p className="text-gray-500 dark:text-gray-400">{error}</p>
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Make sure the DeskSearch server is running</p>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-5 h-5 border-2 border-accent-blue/30 border-t-accent-blue rounded-full animate-spin" />
      </div>
    );
  }

  if (data && data.results.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-400 dark:text-gray-500 mb-2">
          <svg className="w-10 h-10 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
        </div>
        <p className="text-gray-500 dark:text-gray-400">No results found for &ldquo;{query}&rdquo;</p>
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Try a different search term or check your filters</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {data.total} result{data.total !== 1 ? 's' : ''} in {data.query_time_ms}ms
        </p>
        {loading && (
          <div className="w-4 h-4 border-2 border-accent-blue/30 border-t-accent-blue rounded-full animate-spin" />
        )}
      </div>
      <div className="space-y-2">
        {data.results.map((result, index) => (
          <div
            key={result.doc_id}
            className="animate-fadeIn"
            style={{ animationDelay: `${index * 30}ms` }}
          >
            <ResultCard result={result} />
          </div>
        ))}
      </div>
    </div>
  );
}
