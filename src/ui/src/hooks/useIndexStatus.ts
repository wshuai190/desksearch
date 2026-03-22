import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { IndexStatus } from '../types';

export function useIndexStatus(pollInterval = 5000) {
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const fetchStatus = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/status`);
        if (!res.ok) throw new Error(`Status failed: ${res.statusText}`);
        const json: IndexStatus = await res.json();
        if (active) {
          setStatus(json);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to fetch status');
        }
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, pollInterval);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [pollInterval]);

  return { status, error };
}
