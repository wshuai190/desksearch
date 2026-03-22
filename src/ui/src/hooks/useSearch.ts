import { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import type { SearchResponse, SearchFilters } from '../types';

export function useSearch(query: string, filters: SearchFilters) {
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const search = useCallback(async (q: string, f: SearchFilters) => {
    if (!q.trim()) {
      setData(null);
      setLoading(false);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ q: q.trim() });
      if (f.file_types.length > 0) {
        params.set('file_types', f.file_types.join(','));
      }
      if (f.date_from) params.set('date_from', f.date_from);
      if (f.date_to) params.set('date_to', f.date_to);
      if (f.folder) params.set('folder', f.folder);

      const res = await fetch(`${API_BASE_URL}/api/search?${params}`, {
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`Search failed: ${res.statusText}`);

      const json: SearchResponse = await res.json();
      setData(json);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => search(query, filters), 300);
    return () => clearTimeout(timer);
  }, [query, filters, search]);

  return { data, loading, error };
}
