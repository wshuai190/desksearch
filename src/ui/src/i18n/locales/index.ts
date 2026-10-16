/**
 * Locale registry.
 *
 * Every namespace lives in its own file pair (`en/<ns>.ts`, `zh/<ns>.ts`) and
 * default-exports a flat `{ key: string }` map. Keys inside a namespace file do
 * NOT repeat the namespace — it is applied here by `withNs()`, so lookups from
 * components read as `t('search.hero.title')`.
 *
 * Adding a namespace: create both files, import them below, add them to both
 * `prefix` groups. Keys present in `en` but missing in `zh` fall back to
 * English at runtime (see `translate()`).
 */
import enCommon from './en/common';
import enApp from './en/app';
import enSearch from './en/search';
import enFilters from './en/filters';
import enResults from './en/results';
import enOnboarding from './en/onboarding';
import enSettings from './en/settings';
import enIntegrations from './en/integrations';
import enPanels from './en/panels';

import zhCommon from './zh/common';
import zhApp from './zh/app';
import zhSearch from './zh/search';
import zhFilters from './zh/filters';
import zhResults from './zh/results';
import zhOnboarding from './zh/onboarding';
import zhSettings from './zh/settings';
import zhIntegrations from './zh/integrations';
import zhPanels from './zh/panels';

export type Lang = 'zh' | 'en';
export type Dict = Record<string, string>;
export type NamespaceDict = Record<string, string>;

export const LANGS: Lang[] = ['zh', 'en'];

/** Human-readable language names, shown in the language switch. */
export const LANG_LABELS: Record<Lang, string> = {
  zh: '中文',
  en: 'English',
};

function withNs(namespace: string, dict: NamespaceDict): Dict {
  const out: Dict = {};
  for (const [key, value] of Object.entries(dict)) {
    out[`${namespace}.${key}`] = value;
  }
  return out;
}

export const dictionaries: Record<Lang, Dict> = {
  en: {
    ...withNs('common', enCommon),
    ...withNs('app', enApp),
    ...withNs('search', enSearch),
    ...withNs('filters', enFilters),
    ...withNs('results', enResults),
    ...withNs('onboarding', enOnboarding),
    ...withNs('settings', enSettings),
    ...withNs('integrations', enIntegrations),
    ...withNs('panels', enPanels),
  },
  zh: {
    ...withNs('common', zhCommon),
    ...withNs('app', zhApp),
    ...withNs('search', zhSearch),
    ...withNs('filters', zhFilters),
    ...withNs('results', zhResults),
    ...withNs('onboarding', zhOnboarding),
    ...withNs('settings', zhSettings),
    ...withNs('integrations', zhIntegrations),
    ...withNs('panels', zhPanels),
  },
};
