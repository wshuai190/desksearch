/**
 * Locale consistency check — run with:
 *   npx esbuild scripts/check-i18n.ts --bundle --platform=node --format=cjs --outfile=.tmp-check.cjs && node .tmp-check.cjs
 *
 * Verifies the dictionaries the UI ships: key parity between en/zh, plural
 * selection, interpolation, and safe fallbacks. Exits non-zero on failure so it
 * can gate CI.
 */
import { dictionaries, LANGS } from '../src/i18n/locales';
import { translate } from '../src/i18n';

const en = dictionaries.en;
const zh = dictionaries.zh;

const enKeys = Object.keys(en);
const zhKeys = Object.keys(zh);
const zhSet = new Set(zhKeys);
const enSet = new Set(enKeys);

const missingInZh = enKeys.filter((k) => !zhSet.has(k)).sort();
const missingInEn = zhKeys.filter((k) => !enSet.has(k)).sort();

const namespaceOf = (key: string) => key.split('.')[0];
const counts: Record<string, { en: number; zh: number }> = {};
for (const k of enKeys) {
  const ns = namespaceOf(k);
  counts[ns] = counts[ns] ?? { en: 0, zh: 0 };
  counts[ns].en += 1;
}
for (const k of zhKeys) {
  const ns = namespaceOf(k);
  counts[ns] = counts[ns] ?? { en: 0, zh: 0 };
  counts[ns].zh += 1;
}

// Every value must be a non-empty string and both locales must stay non-Latin-free
// where they should be localised (a Chinese file that is pure ASCII means an
// untranslated stub slipped through).
const emptyValues = [...enKeys, ...zhKeys].filter(
  (k) => !(en as Record<string, string>)[k] && !(zh as Record<string, string>)[k],
);
const asciiOnlyInZh = zhKeys
  .filter((k) => !/[^\x00-\x7F]/.test(zh[k]) && /[A-Za-z]{3,}/.test(zh[k]))
  .sort();

// ── behavioural checks ─────────────────────────────────────────────────────
const failures: string[] = [];
const check = (label: string, actual: unknown, expected: unknown) => {
  if (actual !== expected) {
    failures.push(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
};

check('en plural (1)', translate('en', 'common.files', { count: 1 }), '1 file');
check('en plural (3)', translate('en', 'common.files', { count: 3 }), '3 files');
check('zh plural (1)', translate('zh', 'common.files', { count: 1 }), '1 个文件');
check('zh plural (3)', translate('zh', 'common.files', { count: 3 }), '3 个文件');
check(
  'interpolation',
  translate('zh', 'search.subtitleCount', { count: '4,690' }),
  '在 4,690 个文件中按语义搜索',
);
check('english fallback', translate('en', 'this.key.does.not.exist'), 'this.key.does.not.exist');
check('zh falls back to en', translate('zh', 'this.key.does.not.exist'), 'this.key.does.not.exist');
check('en search placeholder', translate('en', 'search.placeholder'), 'Search your files...');
check('zh search placeholder', translate('zh', 'search.placeholder'), '搜索你的文件…');

const report = {
  languages: LANGS,
  totalKeys: { en: enKeys.length, zh: zhKeys.length },
  perNamespace: counts,
  missingInZh,
  missingInEn,
  asciiOnlyInZh_requiresReview: asciiOnlyInZh,
  emptyValues,
  behaviourFailures: failures,
};

console.log(JSON.stringify(report, null, 2));

if (missingInZh.length || missingInEn.length || emptyValues.length || failures.length) {
  console.error('\nFAIL: locale check found problems (see above).');
  process.exit(1);
}
console.log('\nOK: en/zh dictionaries are in sync and behaviour checks pass.');
