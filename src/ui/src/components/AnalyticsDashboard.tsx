import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import { useI18n } from '../i18n';
import type { AnalyticsSummary } from '../types';

function BarChart({ data, formatDate }: {
  data: { date: string; count: number }[];
  formatDate: (value: string | number | Date) => string;
}) {
  const { t } = useI18n();
  if (!data || data.length === 0) return null;
  const max = Math.max(...data.map(d => d.count), 1);

  return (
    <div className="flex items-end gap-1 h-20">
      {data.map((d) => (
        <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group" title={t('panels.analytics.barTooltip', { date: formatDate(d.date), count: d.count })}>
          <div
            className="w-full bg-accent-blue/20 group-hover:bg-accent-blue/50 rounded-t transition-colors"
            style={{ height: `${(d.count / max) * 100}%`, minHeight: d.count > 0 ? '4px' : '0' }}
          />
        </div>
      ))}
    </div>
  );
}

function StatCard({ icon, label, value, sub }: {
  icon: string; label: string; value: string | number; sub?: string;
}) {
  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">{icon}</span>
        <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">{label}</span>
      </div>
      <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function AnalyticsDashboard() {
  const { t, formatNumber, formatDate } = useI18n();
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE_URL}/api/analytics?days=${days}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [days]);

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('panels.analytics.title')}
          </h2>
          <p className="text-sm text-gray-400 mt-0.5">
            {t('panels.analytics.subtitle')}
          </p>
        </div>
        <select
          value={days}
          onChange={e => setDays(Number(e.target.value))}
          className="text-sm border border-gray-200 dark:border-dark-border rounded-lg px-3 py-1.5 bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-blue/50"
        >
          <option value={7}>{t('panels.analytics.range7')}</option>
          <option value={30}>{t('panels.analytics.range30')}</option>
          <option value={90}>{t('panels.analytics.range90')}</option>
        </select>
      </div>

      {loading && (
        <div className="space-y-4 animate-pulse">
          <div className="grid grid-cols-2 gap-4">
            {[1, 2].map(i => (
              <div key={i} className="h-24 bg-gray-100 dark:bg-dark-border rounded-xl" />
            ))}
          </div>
          <div className="h-48 bg-gray-100 dark:bg-dark-border rounded-xl" />
          <div className="h-48 bg-gray-100 dark:bg-dark-border rounded-xl" />
        </div>
      )}

      {!loading && !data && (
        <div className="text-center py-16">
          <div className="text-4xl mb-3">📭</div>
          <p className="text-gray-500 dark:text-gray-400">{t('panels.analytics.emptyTitle')}</p>
        </div>
      )}

      {!loading && data && (
        <div className="space-y-6">
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-4">
            <StatCard
              icon="🔍"
              label={t('panels.analytics.totalSearches')}
              value={formatNumber(data.total_searches)}
              sub={t('panels.analytics.inLastDays', { count: days })}
            />
            <StatCard
              icon="📂"
              label={t('panels.analytics.filesAccessed')}
              value={formatNumber(data.total_clicks)}
              sub={t('panels.analytics.viaSearchResults')}
            />
          </div>

          {/* Search activity chart */}
          {data.search_over_time.length > 1 && (
            <div className="bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
                {t('panels.analytics.searchActivity')}
              </h3>
              <BarChart data={data.search_over_time} formatDate={formatDate} />
              <div className="flex justify-between mt-1">
                <span className="text-[10px] text-gray-400">
                  {data.search_over_time[0]?.date && formatDate(data.search_over_time[0].date)}
                </span>
                <span className="text-[10px] text-gray-400">
                  {data.search_over_time[data.search_over_time.length - 1]?.date &&
                    formatDate(data.search_over_time[data.search_over_time.length - 1].date)}
                </span>
              </div>
            </div>
          )}

          {/* Top searches */}
          {data.top_searches.length > 0 && (
            <div className="bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
                {t('panels.analytics.topSearches')}
              </h3>
              <div className="space-y-2.5">
                {data.top_searches.map((s, i) => {
                  const maxCount = data.top_searches[0]?.count || 1;
                  const pct = Math.round((s.count / maxCount) * 100);
                  return (
                    <div key={s.query} className="flex items-center gap-3">
                      <span className="w-5 text-center text-xs text-gray-400 font-mono flex-shrink-0">
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-gray-800 dark:text-gray-200 truncate font-medium">
                            {s.query}
                          </span>
                          <span className="text-xs text-gray-400 flex-shrink-0 ml-2">
                            {s.count}×
                          </span>
                        </div>
                        <div className="h-1 bg-gray-100 dark:bg-dark-border rounded-full overflow-hidden">
                          <div
                            className="h-full bg-accent-blue/50 rounded-full transition-all"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Recently accessed files */}
          {data.top_files.length > 0 && (
            <div className="bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
                {t('panels.analytics.mostAccessedFiles')}
              </h3>
              <div className="space-y-2">
                {data.top_files.map((f) => (
                  <button
                    key={f.path}
                    onClick={() => fetch(`${API_BASE_URL}/api/open/${encodeURIComponent(f.path)}`)}
                    className="w-full flex items-center gap-3 p-2.5 rounded-lg hover:bg-gray-50 dark:hover:bg-dark-hover transition-colors text-left group"
                  >
                    <span className="text-base flex-shrink-0">📄</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate group-hover:text-accent-blue transition-colors">
                        {f.filename}
                      </div>
                      <div className="text-xs text-gray-400 truncate">
                        {f.path.replace(/^\/Users\/[^/]+/, '~')}
                      </div>
                    </div>
                    <div className="flex-shrink-0 flex items-center gap-1 text-xs text-gray-400">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                      {f.clicks}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {data.total_searches === 0 && (
            <div className="text-center py-12 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-xl">
              <div className="text-4xl mb-3">🔍</div>
              <p className="text-gray-600 dark:text-gray-400 font-medium">{t('panels.analytics.noSearchesYet')}</p>
              <p className="text-sm text-gray-400 mt-1">{t('panels.analytics.searchHistoryHint')}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
