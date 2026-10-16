import type { IndexStatus } from '../types';
import { useI18n } from '../i18n';

function formatLastIndexed(
  dateStr: string | null,
  t: (key: string, params?: Record<string, string | number> & { count?: number }) => string,
  formatDate: (value: string | number | Date, options?: Intl.DateTimeFormatOptions) => string,
): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return t('results.updatedJustNow');
  if (diffMin < 60) return t('results.updatedMinutesAgo', { count: diffMin });
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return t('results.updatedHoursAgo', { count: diffHrs });
  return t('results.updatedOn', { date: formatDate(date) });
}

function formatFileCount(
  n: number,
  t: (key: string, params?: Record<string, string | number> & { count?: number }) => string,
  formatNumber: (value: number) => string,
): string {
  if (n === 0) return t('results.noFilesIndexed');
  return `${formatNumber(n)} ${t(n === 1 ? 'results.filesReadyLabel_one' : 'results.filesReadyLabel', { count: n })}`;
}

interface StatusBarProps {
  status: IndexStatus | null;
  error: string | null;
}

export default function StatusBar({ status, error }: StatusBarProps) {
  const { t, formatNumber, formatDate } = useI18n();

  // Error state
  if (error) {
    return (
      <>
        <div className="hidden sm:block fixed bottom-0 left-0 right-0 px-4 py-2 bg-red-50 dark:bg-red-950/40 border-t border-red-200 dark:border-red-900/50 z-10">
          <div className="max-w-5xl mx-auto flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
            <span className="text-xs text-red-600 dark:text-red-400 font-medium">
              {t('results.notRunning')}
            </span>
            <span className="text-xs text-red-400 dark:text-red-500">
              {t('results.notRunningHint')}
            </span>
          </div>
        </div>
        <div className="sm:hidden mx-3 mb-1 px-3 py-2 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 rounded-lg flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
          <span className="text-xs text-red-600 dark:text-red-400">{t('results.notRunning')}</span>
        </div>
      </>
    );
  }

  if (!status) return null;

  const isIndexing = status.is_indexing;
  const fileCount = status.total_documents;
  const lastIndexed = formatLastIndexed(status.last_indexed, t, formatDate);

  return (
    <>
      {/* Desktop status bar */}
      <div className="hidden sm:block fixed bottom-0 left-0 right-0 px-4 py-2 bg-white/80 dark:bg-dark-surface/80 backdrop-blur-md border-t border-gray-100 dark:border-dark-border z-10">
        <div className="max-w-5xl mx-auto flex items-center justify-between text-xs">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                isIndexing ? 'bg-amber-400 animate-pulse' : 'bg-emerald-500'
              }`} />
              <span className={`font-medium ${
                isIndexing
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-emerald-600 dark:text-emerald-400'
              }`}>
                {isIndexing ? t('results.readingFiles') : formatFileCount(fileCount, t, formatNumber)}
              </span>
            </div>

            {isIndexing && fileCount > 0 && (
              <span className="text-gray-400 dark:text-gray-500 tabular-nums">
                {t('results.doneSoFar', { count: fileCount })}
              </span>
            )}
          </div>

          {lastIndexed && !isIndexing && (
            <span className="text-gray-400 dark:text-gray-500">{lastIndexed}</span>
          )}
        </div>
      </div>

      {/* Mobile: compact inline status */}
      {(isIndexing || fileCount === 0) && (
        <div className="sm:hidden mx-3 mb-1 px-3 py-2 bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-lg flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            isIndexing ? 'bg-amber-400 animate-pulse' : 'bg-gray-300'
          }`} />
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {isIndexing
              ? (fileCount > 0
                ? <>{t('results.readingYourFiles')} {t('results.doneCount', { count: fileCount })}</>
                : t('results.readingYourFiles'))
              : t('results.noFilesIndexedHint')}
          </span>
        </div>
      )}
    </>
  );
}
