import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import type { DashboardStats, ActivityEntry } from '../types';

const TYPE_COLORS: Record<string, string> = {
  PDF:         'bg-red-500',
  Documents:   'bg-blue-500',
  Code:        'bg-green-500',
  Text:        'bg-yellow-500',
  'Web/Config':'bg-purple-500',
  Other:       'bg-gray-500',
};

const TYPE_TEXT_COLORS: Record<string, string> = {
  PDF:         'text-red-500',
  Documents:   'text-blue-500',
  Code:        'text-green-500',
  Text:        'text-yellow-500',
  'Web/Config':'text-purple-500',
  Other:       'text-gray-500',
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

// ── Skeleton components ──────────────────────────────────────────────────────
function SkeletonStatCard() {
  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4 animate-pulse">
      <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-2/3 mb-3" />
      <div className="h-7 bg-gray-200 dark:bg-dark-border rounded w-1/2" />
    </div>
  );
}

function SkeletonPanel() {
  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4 animate-pulse">
      <div className="h-3 bg-gray-200 dark:bg-dark-border rounded w-1/3 mb-4" />
      <div className="space-y-2">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-8 bg-gray-200 dark:bg-dark-border rounded" />
        ))}
      </div>
    </div>
  );
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
      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <SkeletonStatCard key={i} />)}
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          <SkeletonPanel />
          <SkeletonPanel />
        </div>
        <SkeletonPanel />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <div className="w-12 h-12 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
          <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
          </svg>
        </div>
        <p className="text-gray-500 dark:text-gray-400 text-sm">Failed to load dashboard data</p>
      </div>
    );
  }

  const typeEntries = Object.entries(stats.type_breakdown).sort(([, a], [, b]) => b - a);
  const totalTyped = typeEntries.reduce((s, [, v]) => s + v, 0) || 1;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6 animate-fadeIn">
      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Files"
          value={stats.total_documents.toLocaleString()}
          icon="📄"
        />
        <StatCard
          label="Chunks"
          value={stats.total_chunks.toLocaleString()}
          icon="🧩"
          subtitle="indexed segments"
        />
        <StatCard
          label="Index Size"
          value={formatBytes(stats.index_size_mb)}
          icon="💾"
        />
        <StatCard
          label="Status"
          value={stats.is_indexing ? 'Indexing…' : 'Ready'}
          icon={stats.is_indexing ? '⏳' : '✅'}
          valueClass={stats.is_indexing ? 'text-yellow-400' : 'text-green-400'}
          pulse={stats.is_indexing}
        />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* File type breakdown */}
        <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">File Types</h3>
          {typeEntries.length === 0 ? (
            <div className="text-center py-6">
              <div className="text-3xl mb-2">📂</div>
              <p className="text-sm text-gray-400">No files indexed yet</p>
              <p className="text-xs text-gray-300 dark:text-gray-500 mt-1">Add folders in the Folders tab</p>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Stacked bar */}
              <div className="flex h-3 rounded-full overflow-hidden gap-px">
                {typeEntries.map(([type, count]) => (
                  <div
                    key={type}
                    className={`${TYPE_COLORS[type] || 'bg-gray-500'} transition-all`}
                    style={{ width: `${(count / totalTyped) * 100}%` }}
                    title={`${type}: ${count}`}
                  />
                ))}
              </div>
              {/* Legend with counts */}
              <div className="space-y-1 mt-3">
                {typeEntries.map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${TYPE_COLORS[type] || 'bg-gray-500'}`} />
                      <span className="text-gray-600 dark:text-gray-300">{type}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`font-medium ${TYPE_TEXT_COLORS[type] || 'text-gray-400'}`}>{count}</span>
                      <span className="text-gray-300 dark:text-gray-600 w-10 text-right">
                        {Math.round((count / totalTyped) * 100)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Watched folders */}
        <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Watched Folders</h3>
          {stats.watched_folders.length === 0 ? (
            <div className="text-center py-6">
              <div className="text-3xl mb-2">📁</div>
              <p className="text-sm text-gray-400">No folders configured</p>
              <p className="text-xs text-gray-300 dark:text-gray-500 mt-1">Go to the Folders tab to add some</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-52 overflow-y-auto">
              {stats.watched_folders.map((f) => (
                <div
                  key={f.path}
                  className="flex items-start justify-between py-2 border-b border-gray-50 dark:border-dark-border last:border-0"
                >
                  <div className="flex items-start gap-2 flex-1 min-w-0">
                    <span className="text-base mt-0.5">📁</span>
                    <div className="min-w-0">
                      <div className="text-sm text-gray-700 dark:text-gray-300 truncate" title={f.path}>
                        {f.path.replace(/^\/Users\/[^/]+/, '~')}
                      </div>
                      {f.last_indexed && (
                        <div className="text-xs text-gray-400 mt-0.5">Indexed {timeAgo(f.last_indexed)}</div>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end ml-3 shrink-0">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{f.file_count}</span>
                    <span className="text-xs text-gray-400">files</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent activity */}
      <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Recent Indexing Activity</h3>
        {activity.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-3xl mb-2">🕐</div>
            <p className="text-sm text-gray-400">No recent activity</p>
          </div>
        ) : (
          <div className="space-y-0 max-h-80 overflow-y-auto">
            {activity.map((entry, i) => (
              <div
                key={`${entry.path}-${i}`}
                className="flex items-center justify-between py-2 border-b border-gray-50 dark:border-dark-border last:border-0 hover:bg-gray-50 dark:hover:bg-dark-hover/50 -mx-1 px-1 rounded transition-colors"
              >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-dark-hover text-gray-600 dark:text-gray-400 font-mono shrink-0">
                    .{entry.file_type}
                  </span>
                  <span className="truncate text-sm text-gray-700 dark:text-gray-300">{entry.filename}</span>
                </div>
                <div className="flex items-center gap-3 ml-3 shrink-0 text-xs text-gray-400">
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

function StatCard({
  label, value, icon, subtitle, valueClass, pulse,
}: {
  label: string;
  value: string;
  icon?: string;
  subtitle?: string;
  valueClass?: string;
  pulse?: boolean;
}) {
  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
        {icon && <span className="text-lg">{icon}</span>}
      </div>
      <div className={`text-2xl font-semibold ${valueClass || 'text-gray-900 dark:text-white'} ${pulse ? 'animate-pulse' : ''}`}>
        {value}
      </div>
      {subtitle && <div className="text-xs text-gray-400 mt-0.5">{subtitle}</div>}
    </div>
  );
}
