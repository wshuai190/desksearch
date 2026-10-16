/**
 * Language switch (中文 / English).
 *
 * Two visual variants:
 *   <LanguageToggle />                     icon + target code — for headers
 *   <LanguageToggle showLabel variant="row" /> full row — for the sidebar / settings
 */
import { useI18n } from '../i18n';
import { LANG_LABELS } from '../i18n/locales';

interface Props {
  /** Render a text label next to the icon (sidebar / settings style). */
  showLabel?: boolean;
  /** `row` fills the container like the other sidebar entries. */
  variant?: 'row' | 'icon';
  className?: string;
}

export default function LanguageToggle({ showLabel = false, variant = 'icon', className = '' }: Props) {
  const { lang, toggleLang, t } = useI18n();
  const next = lang === 'zh' ? 'en' : 'zh';
  const label = LANG_LABELS[next];
  const title = t('common.languageSwitchTo', { lang: label });

  const isRow = variant === 'row';

  return (
    <button
      type="button"
      onClick={toggleLang}
      title={title}
      aria-label={title}
      className={
        isRow
          ? `w-full flex items-center gap-2.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors min-h-0 px-3 py-2 ${className}`
          : `flex items-center gap-1 px-2 py-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors ${className}`
      }
    >
      <svg
        className={isRow ? 'flex-shrink-0 w-4 h-4' : 'w-4 h-4'}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.8}
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 21a9 9 0 100-18 9 9 0 000 18zM3.6 9h16.8M3.6 15h16.8M12 3c2.5 2.4 3.8 5.4 3.8 9s-1.3 6.6-3.8 9c-2.5-2.4-3.8-5.4-3.8-9S9.5 5.4 12 3z"
        />
      </svg>
      {showLabel ? (
        <span className="text-[13px] truncate">{label}</span>
      ) : (
        <span className="text-[11px] font-semibold tracking-tight">{lang === 'zh' ? 'EN' : '中'}</span>
      )}
    </button>
  );
}
