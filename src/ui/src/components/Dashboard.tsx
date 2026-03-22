import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { DashboardStats, ActivityEntry } from '../types';

const TYPE_COLORS: Record<string, string> = {
  PDF: 'bg-red-500',
  Documents: 'bg-blue-500',
  Code: 'bg-green-500',
  Text: 'bg-yellow-500',
  'Web/Config': 'bg-purple-500',
  Other: 'bg-gray-500',
};

function formatBytes(mb: number): string {
  if (mb < 1) return `${Math.round(mb * 1024)} KB`;
  return `${mb.toFixed(1)} MB`;
}

function timeAgo(dateStr: string): string {
  const d = new Date(dateStr);
  const now = Date.now();
  const diff = now - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [dashRes, actRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/dashboard`),
          fetch(`${API_BASE_URL}/api/activity?limit=20`),
        ]);
        if (!active) return;
        if (dashRes.ok) setStats(await dashRes.json());
        if (actRes.ok) {
          const data = await actRes.json();
          setActivity(data.entries || []);
        }
      } catch {
        // ignore
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-400">Loading dashboard...</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-400">Failed to load dashboard data</div>
      </div>
    );
  }

  const typeEntries = Object.entries(stats.type_breakdown);
  const totalTyped = typeEntries.reduce((s, [, v]) => s + v, 0) || 1;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Files" value={stats.total_documents.toLocaleString()} />
        <StatCard label="Total Chunks" value={stats.total_chunks.toLocaleString()} />
        <StatCard label="Index Size" value={formatBytes(stats.index_size_mb)} />
        <StatCard
          label="Status"
          value={stats.is_indexing ? 'Indexing...' : 'Ready'}
          valueClass={stats.is_indexing ? 'text-yellow-400' : 'text-green-400'}
        />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* File type breakdown */}
        <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">File Types</h3>
          {typeEntries.length === 0 ? (
            <div className="text-gray-400 text-sm">No files indexed yet</div>
          ) : (
            <div className="space-y-2">
              {/* Bar chart */}
              <div className="flex h-6 rounded-full overflow-hidden">
                {typeEntries.map(([type, count]) => (
                  <div
                    key={type}
                    className={`${TYPE_COLORS[type] || 'bg-gray-500'} transition-all`}
                    style={{ width: `${(count / totalTyped) * 100}%` }}
                    title={`${type}: ${count}`}
                  />
                ))}
              </div>
              {/* Legend */}
              <div className="flex flex-wrap gap-3 mt-3">
                {typeEntries.map(([type, count]) => (
                  <div key={type} className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300">
                    <span className={`w-2.5 h-2.5 rounded-full ${TYPE_COLORS[type] || 'bg-gray-500'}`} />
                    {type} ({count})
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Watched folders */}
        <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Watched Folders</h3>
          {stats.watched_folders.length === 0 ? (
            <div className="text-gray-400 text-sm">No folders configured</div>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {stats.watched_folders.map((f) => (
                <div key={f.path} className="flex items-center justify-between text-sm py-1.5 border-b border-gray-100 dark:border-dark-border last:border-0">
                  <div className="truncate flex-1 text-gray-700 dark:text-gray-300" title={f.path}>
                    {f.path.replace(/^\/Users\/[^/]+/, '~')}
                  </div>
                  <div className="flex items-center gap-3 ml-3 shrink-0 text-xs text-gray-500">
                    <span>{f.file_count} files</span>
                    {f.last_indexed && <span>{timeAgo(f.last_indexed)}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent activity */}
      <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Recent Indexing Activity</h3>
        {activity.length === 0 ? (
          <div className="text-gray-400 text-sm">No recent activity</div>
        ) : (
          <div className="space-y-1 max-h-80 overflow-y-auto">
            {activity.map((entry, i) => (
              <div key={`${entry.path}-${i}`} className="flex items-center justify-between text-sm py-1.5 border-b border-gray-100 dark:border-dark-border last:border-0">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-dark-hover text-gray-600 dark:text-gray-400 font-mono shrink-0">
                    .{entry.file_type}
                  </span>
                  <span className="truncate text-gray-700 dark:text-gray-300">{entry.filename}</span>
                </div>
                <div className="flex items-center gap-3 ml-3 shrink-0 text-xs text-gray-500">
                  <span>{entry.num_chunks} chunks</span>
                  <span>{timeAgo(entry.indexed_time)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className={`text-2xl font-semibold ${valueClass || 'text-gray-900 dark:text-white'}`}>{value}</div>
    </div>
  );
}
