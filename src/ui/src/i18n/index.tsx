/**
 * Tiny, dependency-free i18n layer for the DeskSearch UI.
 *
 * Usage:
 *
 *   const { t, lang, setLang, toggleLang, formatNumber, formatDate } = useI18n();
 *   <h1>{t('search.hero.title')}</h1>
 *   <p>{t('search.subtitle', { count: 1234 })}</p>
 *
 * Conventions:
 *  - Keys are `<namespace>.<key>`, namespaces are registered in `locales/index.ts`.
 *  - `{placeholder}` tokens are substituted from the second argument.
 *  - When `params.count` is a number the plural form is chosen: `<key>_one` for
 *    1 and `<key>_other` otherwise (the bare key is used when neither exists):
 *      en: { 'count.files': 'files', 'count.files_one': '{count} file', 'count.files_other': '{count} files' }
 *  - Missing keys fall back to English, then to the key itself (never crashes).
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { dictionaries, LANGS, LANG_LABELS, type Dict, type Lang } from './locales';

export type { Lang };
export { LANGS, LANG_LABELS };
// `count` drives simple plural selection (`<key>_one`); it may also be passed
// pre-formatted (e.g. via formatNumber()) as a string.
export type TranslateParams = Record<string, string | number> & { count?: number | string };

export interface I18nValue {
  /** Active language code. */
  lang: Lang;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  /** Translate a key with optional `{placeholder}` params. */
  t: (key: string, params?: TranslateParams) => string;
  /** Locale-aware number formatting (1,234 / 1,234). */
  formatNumber: (value: number) => string;
  /** Locale-aware date formatting. */
  formatDate: (value: string | number | Date, options?: Intl.DateTimeFormatOptions) => string;
}

const STORAGE_KEY = 'desksearch:lang';
const I18nContext = createContext<I18nValue | null>(null);

function isLang(value: unknown): value is Lang {
  return typeof value === 'string' && (LANGS as string[]).includes(value);
}

function localeOf(lang: Lang): string {
  return lang === 'zh' ? 'zh-CN' : 'en-US';
}

/** Stored choice → browser preference → English. */
export function detectLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    /* localStorage unavailable (private mode) — fall through */
  }
  const nav = typeof navigator !== 'undefined' ? navigator.language || '' : '';
  return nav.toLowerCase().startsWith('zh') ? 'zh' : 'en';
}

function persist(lang: Lang): void {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* ignore */
  }
}

/** Pure lookup used by the provider and by tests. */
export function translate(lang: Lang, key: string, params?: TranslateParams): string {
  const primary: Dict = dictionaries[lang] ?? {};
  const fallback: Dict = dictionaries.en ?? {};

  let lookup = key;
  if (typeof params?.count === 'number') {
    // Simple plural selection: `<key>_one` for 1, `<key>_other` otherwise.
    // The bare key stays the last resort so pages that only define a single
    // form keep working.
    const variant = params.count === 1 ? `${key}_one` : `${key}_other`;
    if (primary[variant] !== undefined || fallback[variant] !== undefined) {
      lookup = variant;
    }
  }

  let text = primary[lookup] ?? fallback[lookup] ?? key;

  if (params) {
    text = text.replace(/\{(\w+)\}/g, (match, name: string) =>
      params[name] === undefined ? match : String(params[name]),
    );
  }
  return text;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang);

  // Keep <html lang> in sync for a11y, correct hyphenation and font fallback
  // (Chinese text renders better when the document language is declared).
  useEffect(() => {
    document.documentElement.lang = localeOf(lang);
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    persist(next);
  }, []);

  const toggleLang = useCallback(() => {
    setLangState((prev) => {
      const next: Lang = prev === 'zh' ? 'en' : 'zh';
      persist(next);
      return next;
    });
  }, []);

  const value = useMemo<I18nValue>(() => {
    const locale = localeOf(lang);
    return {
      lang,
      setLang,
      toggleLang,
      t: (key, params) => translate(lang, key, params),
      formatNumber: (n) => n.toLocaleString(locale),
      formatDate: (v, options) =>
        new Date(v).toLocaleDateString(locale, options ?? { year: 'numeric', month: 'short', day: 'numeric' }),
    };
  }, [lang, setLang, toggleLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useI18n() must be used inside <I18nProvider> (see src/main.tsx)');
  }
  return ctx;
}
