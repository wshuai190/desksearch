/**
 * IntegrationsPanel — Settings section for all external tool integrations.
 *
 * Cards:
 *  1. API Key         — bearer-token auth for /api/v1/search
 *  2. Alfred/Raycast  — script filter JSON endpoint, ready to use
 *  3. Slack           — slash-command webhook URL + setup guide
 *  4. Browser Bookmarks — one-click sync with status
 *  5. Email Import    — drag-and-drop .mbox/.eml upload
 *  6. Webhooks        — outbound notification URLs
 */

import { useState, useRef, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { useI18n } from '../i18n';
import type { BrowserSyncResult, EmailImportResult } from '../types';

// ── Tiny helpers ────────────────────────────────────────────────────────────

function Badge({ on, label }: { on: boolean; label?: string }) {
  const { t } = useI18n();
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium ${
        on
          ? 'bg-green-500/12 text-green-600 dark:text-green-400'
          : 'bg-gray-100 dark:bg-dark-hover text-gray-500 dark:text-gray-400'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${on ? 'bg-green-500' : 'bg-gray-400'}`} />
      {label ?? (on ? t('common.enabled') : t('integrations.badge.notConfigured'))}
    </span>
  );
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };
  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md bg-gray-100 dark:bg-dark-hover text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-dark-border transition-colors"
    >
      {copied ? (
        <>
          <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          {t('common.copied')}
        </>
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          {label ?? t('common.copy')}
        </>
      )}
    </button>
  );
}

function CodeSnippet({ code }: { code: string }) {
  return (
    <div className="relative group">
      <pre className="text-xs bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border rounded-md px-3 py-2 font-mono overflow-x-auto text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-all">
        {code}
      </pre>
      <div className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

function SectionCard({
  icon, title, badge, children,
}: {
  icon: React.ReactNode;
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-dark-border">
        <div className="flex items-center gap-2.5">
          <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-gray-100 dark:bg-dark-hover text-gray-600 dark:text-gray-300">
            {icon}
          </span>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h3>
        </div>
        {badge}
      </div>
      <div className="px-4 py-4 space-y-3">{children}</div>
    </div>
  );
}

function Instruction({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5">
      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-accent-blue/10 text-accent-blue text-[11px] font-bold flex items-center justify-center mt-0.5">
        {step}
      </span>
      <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">{children}</p>
    </div>
  );
}

// ── 1. API Key Card ──────────────────────────────────────────────────────────

interface ApiKeyCardProps {
  apiKey: string | null | undefined;
  port: number;
  onUpdated: (newKey: string | null) => void;
}

function ApiKeyCard({ apiKey, port, onUpdated }: ApiKeyCardProps) {
  const { t } = useI18n();
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const maskedKey = apiKey
    ? `${apiKey.slice(0, 6)}${'•'.repeat(Math.max(0, apiKey.length - 10))}${apiKey.slice(-4)}`
    : null;

  const regenerate = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/api-key/regenerate`, { method: 'POST' });
      const data = await res.json();
      onUpdated(data.api_key);
      setMsg({ type: 'ok', text: t('integrations.apiKey.msgGenerated') });
      setRevealed(true);
    } catch {
      setMsg({ type: 'err', text: t('integrations.apiKey.msgRegenFailed') });
    } finally {
      setLoading(false);
    }
  };

  const clearKey = async () => {
    setLoading(true);
    setMsg(null);
    try {
      await fetch(`${API_BASE_URL}/api/v1/api-key`, { method: 'DELETE' });
      onUpdated(null);
      setMsg({ type: 'ok', text: t('integrations.apiKey.msgRemoved') });
    } catch {
      setMsg({ type: 'err', text: t('integrations.apiKey.msgClearFailed') });
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard
      title={t('integrations.apiKey.title')}
      badge={
        <Badge
          on={!!apiKey}
          label={apiKey ? t('integrations.apiKey.badge.protected') : t('integrations.apiKey.badge.open')}
        />
      }
      icon={
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
        </svg>
      }
    >
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('integrations.apiKey.descBefore')}{' '}
        <code className="bg-gray-100 dark:bg-dark-hover px-1 rounded text-gray-700 dark:text-gray-300">/api/v1/search</code>{' '}
        {t('integrations.apiKey.descAfter')}
      </p>

      {apiKey ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border rounded-lg px-3 py-2 font-mono text-gray-700 dark:text-gray-300 break-all">
              {revealed ? apiKey : maskedKey}
            </code>
            <button
              onClick={() => setRevealed(!revealed)}
              className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-hover transition-colors"
              title={revealed ? t('integrations.apiKey.hide') : t('integrations.apiKey.show')}
            >
              {revealed ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <CopyButton text={apiKey} label={t('integrations.apiKey.copyKey')} />
            <CopyButton
              text={`Authorization: Bearer ${apiKey}`}
              label={t('integrations.apiKey.copyHeader')}
            />
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-gray-50 dark:bg-dark-bg border border-dashed border-gray-200 dark:border-dark-border px-3 py-2 text-xs text-gray-400">
          {t('integrations.apiKey.empty')}
        </div>
      )}

      {msg && (
        <p className={`text-xs ${msg.type === 'ok' ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={regenerate}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-50 transition-colors"
        >
          {loading
            ? t('integrations.apiKey.generating')
            : apiKey
              ? t('integrations.apiKey.regenerate')
              : t('integrations.apiKey.generate')}
        </button>
        {apiKey && (
          <button
            onClick={clearKey}
            disabled={loading}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-dark-hover disabled:opacity-50 transition-colors"
          >
            {t('integrations.apiKey.removeKey')}
          </button>
        )}
      </div>

      {apiKey && (
        <div className="pt-1 border-t border-gray-100 dark:border-dark-border">
          <p className="text-[11px] text-gray-400 mb-1.5">{t('integrations.apiKey.usageInCurl')}</p>
          <CodeSnippet code={`curl -H "Authorization: Bearer ${apiKey}" \\\n  "http://localhost:${port}/api/v1/search?q=your+query"`} />
        </div>
      )}
    </SectionCard>
  );
}

// ── 2. Alfred / Raycast Card ─────────────────────────────────────────────────

function AlfredCard({ port, apiKey }: { port: number; apiKey?: string | null }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const endpointUrl = `http://localhost:${port}/api/alfred/search?q={{query}}`;
  const curlExample = `curl "http://localhost:${port}/api/alfred/search?q=meeting+notes"`;

  return (
    <SectionCard
      title={t('integrations.alfred.title')}
      badge={<Badge on={true} label={t('integrations.alfred.badge')} />}
      icon={
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      }
    >
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('integrations.alfred.description')}
      </p>

      <div>
        <p className="text-[11px] text-gray-400 uppercase tracking-wide font-medium mb-1">{t('integrations.alfred.scriptFilterUrl')}</p>
        <div className="flex items-start gap-2">
          <code className="flex-1 text-xs bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border rounded-lg px-3 py-2 font-mono text-gray-700 dark:text-gray-300 break-all">
            {endpointUrl}
          </code>
          <CopyButton text={endpointUrl} />
        </div>
      </div>

      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-accent-blue hover:underline"
      >
        <svg
          className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        {open ? t('integrations.setup.hideGuide') : t('integrations.setup.showGuide')}
      </button>

      {open && (
        <div className="space-y-2.5 pt-1 border-t border-gray-100 dark:border-dark-border">
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300">{t('integrations.alfred.workflowTitle')}</p>
          <Instruction step={1}>{t('integrations.alfred.step1')}</Instruction>
          <Instruction step={2}>
            {t('integrations.alfred.step2Add')}{' '}
            <strong>{t('integrations.alfred.termScriptFilter')}</strong>{' '}
            {t('integrations.alfred.step2SetLanguage')} <em>bash</em>{t('integrations.alfred.step2ScriptTo')}
          </Instruction>
          <CodeSnippet
            code={`curl -s "http://localhost:${port}/api/alfred/search?q={query}${apiKey ? `&key=${apiKey}` : ''}"`}
          />
          <Instruction step={3}>
            {t('integrations.alfred.step3Add')}{' '}
            <strong>{t('integrations.alfred.termOpenFile')}</strong>{' '}
            {t('integrations.alfred.step3Rest')}
          </Instruction>

          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 pt-2">{t('integrations.alfred.raycastTitle')}</p>
          <Instruction step={1}>{t('integrations.alfred.raycastStep1')}</Instruction>
          <Instruction step={2}>{t('integrations.alfred.raycastStep2')}</Instruction>
          <CodeSnippet
            code={`#!/bin/bash\n# @raycast.schemaVersion 1\n# @raycast.title DeskSearch\n# @raycast.argument1 { "type": "text", "placeholder": "Query" }\ncurl -s "http://localhost:${port}/api/alfred/search?q=$1" | jq -r '.items[].title'`}
          />

          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 pt-2">{t('integrations.alfred.testFromTerminal')}</p>
          <CodeSnippet code={curlExample} />
        </div>
      )}
    </SectionCard>
  );
}

// ── 3. Slack Card ────────────────────────────────────────────────────────────

interface SlackCardProps {
  port: number;
  slackWebhookUrl: string | null | undefined;
  onSaved: (url: string | null) => void;
}

function SlackCard({ port, slackWebhookUrl, onSaved }: SlackCardProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState(slackWebhookUrl || '');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const slashCommandEndpoint = `http://localhost:${port}/api/integrations/slack/search`;

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slack_webhook_url: url.trim() || '' }),
      });
      if (res.ok) {
        onSaved(url.trim() || null);
        setMsg({ type: 'ok', text: t('integrations.saved') });
      } else {
        setMsg({ type: 'err', text: t('integrations.saveFailed') });
      }
    } catch {
      setMsg({ type: 'err', text: t('integrations.networkError') });
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard
      title={t('integrations.slack.title')}
      badge={<Badge on={!!slackWebhookUrl} />}
      icon={
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      }
    >
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('integrations.slack.descBefore')}{' '}
        <code className="bg-gray-100 dark:bg-dark-hover px-1 rounded">/search</code>{' '}
        {t('integrations.slack.descAfter')}
      </p>

      <div>
        <p className="text-[11px] text-gray-400 uppercase tracking-wide font-medium mb-1">{t('integrations.slack.requestUrlLabel')}</p>
        <div className="flex items-start gap-2">
          <code className="flex-1 text-xs bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border rounded-lg px-3 py-2 font-mono text-gray-700 dark:text-gray-300 break-all">
            {slashCommandEndpoint}
          </code>
          <CopyButton text={slashCommandEndpoint} />
        </div>
        <p className="text-[11px] text-gray-400 mt-1">{t('integrations.slack.requestUrlHint')}</p>
      </div>

      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-accent-blue hover:underline"
      >
        <svg
          className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        {open ? t('integrations.setup.hideGuide') : t('integrations.setup.showFullGuide')}
      </button>

      {open && (
        <div className="space-y-2.5 pt-1 border-t border-gray-100 dark:border-dark-border">
          <Instruction step={1}>
            {t('integrations.slack.step1Before')}{' '}
            <a href="https://api.slack.com/apps" target="_blank" rel="noopener noreferrer" className="text-accent-blue hover:underline">api.slack.com/apps</a>{' '}
            {t('integrations.slack.step1After')}
          </Instruction>
          <Instruction step={2}>
            {t('integrations.slack.step2Click')}{' '}
            <strong>{t('integrations.slack.step2SlashCommands')}</strong> {t('integrations.slack.step2Arrow')}{' '}
            <strong>{t('integrations.slack.step2CreateNewCommand')}</strong>
            {t('integrations.slack.step2SetCommand')}{' '}
            <code className="bg-gray-100 dark:bg-dark-hover px-1 rounded">/search</code>
            {t('integrations.slack.step2End')}
          </Instruction>
          <Instruction step={3}>{t('integrations.slack.step3')}</Instruction>
          <Instruction step={4}>
            {t('integrations.slack.step4Before')}{' '}
            <code className="bg-gray-100 dark:bg-dark-hover px-1 rounded">/search meeting notes</code>{' '}
            {t('integrations.slack.step4After')}
          </Instruction>

          <div className="pt-1">
            <p className="text-[11px] text-gray-400 mb-1.5">
              {t('integrations.slack.outgoingWebhook')}
            </p>
            <input
              type="url"
              value={url}
              onChange={e => { setUrl(e.target.value); setMsg(null); }}
              placeholder={t('integrations.slack.webhookPlaceholder')}
              className="w-full text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono"
            />
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={save}
                disabled={saving}
                className="text-xs px-3 py-1.5 rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-50 transition-colors"
              >
                {saving ? t('common.saving') : t('integrations.slack.saveWebhook')}
              </button>
              {msg && (
                <span className={`text-xs ${msg.type === 'ok' ? 'text-green-500' : 'text-red-500'}`}>
                  {msg.text}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

// ── 4. Browser Bookmarks Card ────────────────────────────────────────────────

function BrowserBookmarksCard() {
  const { t, formatNumber, formatDate } = useI18n();
  const [status, setStatus] = useState<'idle' | 'syncing' | 'done' | 'error'>('idle');
  const [result, setResult] = useState<BrowserSyncResult | null>(null);
  const [lastSync, setLastSync] = useState<string | null>(
    () => localStorage.getItem('desksearch:browserSyncTime')
  );

  const sync = async () => {
    setStatus('syncing');
    setResult(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/integrations/browser/sync`, { method: 'POST' });
      const data: BrowserSyncResult = await res.json();
      setResult(data);
      setStatus('done');
      const now = new Date().toISOString();
      setLastSync(now);
      localStorage.setItem('desksearch:browserSyncTime', now);
    } catch {
      setStatus('error');
    }
  };

  return (
    <SectionCard
      title={t('integrations.bookmarks.title')}
      badge={
        <Badge
          on={lastSync !== null}
          label={lastSync ? t('integrations.bookmarks.synced') : t('integrations.bookmarks.notSynced')}
        />
      }
      icon={
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
        </svg>
      }
    >
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('integrations.bookmarks.description')}
      </p>

      <div className="rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border px-3 py-2 space-y-1">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-gray-500 dark:text-gray-400">{t('integrations.bookmarks.chrome')}</span>
          <span className="text-gray-400 font-mono">~/Library/Application Support/Google/Chrome/Default/Bookmarks</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-gray-500 dark:text-gray-400">{t('integrations.bookmarks.firefox')}</span>
          <span className="text-gray-400 font-mono">~/Library/Application Support/Firefox/Profiles/*/places.sqlite</span>
        </div>
      </div>

      {result && (
        <div className={`flex items-center gap-3 text-xs px-3 py-2 rounded-lg ${
          result.errors > 0 ? 'bg-yellow-50 dark:bg-yellow-900/10 text-yellow-700 dark:text-yellow-400' : 'bg-green-50 dark:bg-green-900/10 text-green-700 dark:text-green-400'
        }`}>
          {result.bookmarks_found === 0 ? (
            <span>{t('integrations.bookmarks.noResults')}</span>
          ) : (
            <>
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              <span>
                {t('integrations.bookmarks.indexed', {
                  indexed: formatNumber(result.bookmarks_indexed),
                  found: formatNumber(result.bookmarks_found),
                })}
                {result.errors > 0 && ` ${t('integrations.errors', { count: result.errors })}`}
              </span>
            </>
          )}
        </div>
      )}

      {status === 'error' && (
        <p className="text-xs text-red-500">{t('integrations.bookmarks.syncFailed')}</p>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={sync}
          disabled={status === 'syncing'}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-50 transition-colors"
        >
          {status === 'syncing' ? (
            <>
              <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {t('integrations.bookmarks.syncing')}
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {t('integrations.bookmarks.sync')}
            </>
          )}
        </button>
        {lastSync && (
          <span className="text-[11px] text-gray-400">
            {t('integrations.bookmarks.lastSync', {
              time: formatDate(lastSync, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              }),
            })}
          </span>
        )}
      </div>
    </SectionCard>
  );
}

// ── 5. Email Import Card ─────────────────────────────────────────────────────

function EmailImportCard() {
  const { t, formatNumber } = useI18n();
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<EmailImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = useCallback(async (file: File) => {
    if (!file.name.endsWith('.mbox') && !file.name.endsWith('.eml')) {
      setError(t('integrations.email.onlyMboxEml'));
      return;
    }
    setUploading(true);
    setResult(null);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE_URL}/api/integrations/email/import`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || t('integrations.email.uploadFailed'));
      } else {
        setResult(data as EmailImportResult);
      }
    } catch {
      setError(t('integrations.email.uploadFailedBackend'));
    } finally {
      setUploading(false);
    }
  }, [t]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  }, [upload]);

  return (
    <SectionCard
      title={t('integrations.email.title')}
      badge={<Badge on={false} label={t('integrations.email.formats')} />}
      icon={
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      }
    >
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('integrations.email.descBefore')}{' '}
        <code className="bg-gray-100 dark:bg-dark-hover px-1 rounded">.mbox</code>{' '}
        {t('integrations.or')}{' '}
        <code className="bg-gray-100 dark:bg-dark-hover px-1 rounded">.eml</code>{' '}
        {t('integrations.email.descAfter')}
      </p>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        className={`relative border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
          dragging
            ? 'border-accent-blue bg-accent-blue/5'
            : 'border-gray-200 dark:border-dark-border hover:border-accent-blue/50 hover:bg-gray-50 dark:hover:bg-dark-hover/30'
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".mbox,.eml"
          className="hidden"
          onChange={e => { if (e.target.files?.[0]) upload(e.target.files[0]); }}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-2">
            <svg className="w-7 h-7 animate-spin text-accent-blue" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-xs text-gray-500">{t('integrations.email.indexing')}</span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <svg className="w-7 h-7 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {t('integrations.email.dropBefore')} <strong>.mbox</strong> {t('integrations.or')}{' '}
              <strong>.eml</strong> {t('integrations.email.dropAfter')}{' '}
              <span className="text-accent-blue">{t('integrations.email.browse')}</span>
            </span>
          </div>
        )}
      </div>

      {result && (
        <div className={`text-xs px-3 py-2 rounded-lg ${
          result.errors > 0 ? 'bg-yellow-50 dark:bg-yellow-900/10 text-yellow-700 dark:text-yellow-400' : 'bg-green-50 dark:bg-green-900/10 text-green-700 dark:text-green-400'
        }`}>
          <strong>{result.filename}</strong>{' '}
          {t('integrations.email.indexed', {
            indexed: formatNumber(result.emails_indexed),
            found: formatNumber(result.emails_found),
          })}
          {result.errors > 0 && ` ${t('integrations.errors', { count: result.errors })}`}
        </div>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </SectionCard>
  );
}

// ── 6. Webhooks Card ─────────────────────────────────────────────────────────

interface WebhooksCardProps {
  webhookUrls: string[];
  onUpdated: (urls: string[]) => void;
}

function WebhooksCard({ webhookUrls, onUpdated }: WebhooksCardProps) {
  const { t } = useI18n();
  const [urls, setUrls] = useState<string[]>(webhookUrls);
  const [newUrl, setNewUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const save = async (next: string[]) => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/webhooks`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ webhook_urls: next }),
      });
      const data = await res.json();
      if (res.ok) {
        onUpdated(data.webhook_urls);
        setUrls(data.webhook_urls);
        setMsg({ type: 'ok', text: t('integrations.saved') });
      } else {
        setMsg({ type: 'err', text: data.detail || t('integrations.saveFailed') });
      }
    } catch {
      setMsg({ type: 'err', text: t('integrations.networkError') });
    } finally {
      setSaving(false);
    }
  };

  const add = () => {
    const trimmed = newUrl.trim();
    if (!trimmed || urls.includes(trimmed)) return;
    const next = [...urls, trimmed];
    setUrls(next);
    setNewUrl('');
    save(next);
  };

  const remove = (url: string) => {
    const next = urls.filter(u => u !== url);
    setUrls(next);
    save(next);
  };

  const test = async (url: string) => {
    setTesting(url);
    setTestResults(r => ({ ...r, [url]: 'testing' }));
    try {
      const res = await fetch(`${API_BASE_URL}/api/webhooks/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (res.ok && data.delivered) {
        setTestResults(r => ({ ...r, [url]: `✓ ${data.http_status}` }));
      } else {
        setTestResults(r => ({ ...r, [url]: `✗ ${res.status}` }));
      }
    } catch {
      setTestResults(r => ({ ...r, [url]: t('integrations.webhooks.testFailed') }));
    } finally {
      setTesting(null);
    }
  };

  return (
    <SectionCard
      title={t('integrations.webhooks.title')}
      badge={
        <Badge
          on={urls.length > 0}
          label={
            urls.length > 0
              ? t('integrations.webhooks.count', { count: urls.length })
              : t('integrations.webhooks.noneSet')
          }
        />
      }
      icon={
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
      }
    >
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('integrations.webhooks.description')}
      </p>

      {/* URL list */}
      {urls.length > 0 && (
        <ul className="space-y-1.5">
          {urls.map(url => (
            <li key={url} className="flex items-center gap-2 bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border rounded-lg px-3 py-1.5">
              <span className="flex-1 text-xs font-mono text-gray-700 dark:text-gray-300 truncate" title={url}>
                {url}
              </span>
              {testResults[url] && (
                <span className={`text-[11px] font-medium ${testResults[url].startsWith('✓') ? 'text-green-500' : testResults[url] === 'testing' ? 'text-gray-400' : 'text-red-500'}`}>
                  {testResults[url] === 'testing' ? t('integrations.webhooks.testing') : testResults[url]}
                </span>
              )}
              <button
                onClick={() => test(url)}
                disabled={testing === url}
                className="text-[11px] px-2 py-0.5 rounded bg-gray-100 dark:bg-dark-hover text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors disabled:opacity-50"
              >
                {t('integrations.webhooks.test')}
              </button>
              <button
                onClick={() => remove(url)}
                className="p-0.5 text-gray-400 hover:text-red-500 transition-colors"
                title={t('common.remove')}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Add URL */}
      <div className="flex gap-2">
        <input
          type="url"
          value={newUrl}
          onChange={e => setNewUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
          placeholder={t('integrations.webhooks.urlPlaceholder')}
          className="flex-1 text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-accent-blue/50 font-mono"
        />
        <button
          onClick={add}
          disabled={!newUrl.trim() || saving}
          className="text-xs px-3 py-2 rounded-lg bg-accent-blue text-white hover:bg-accent-blue-hover disabled:opacity-40 transition-colors"
        >
          {t('common.add')}
        </button>
      </div>

      {msg && (
        <p className={`text-xs ${msg.type === 'ok' ? 'text-green-500' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}

      {/* Payload preview */}
      <div className="pt-1 border-t border-gray-100 dark:border-dark-border">
        <p className="text-[11px] text-gray-400 mb-1.5">{t('integrations.webhooks.payloadLabel')}</p>
        <CodeSnippet code={`{\n  "event": "indexing_complete",\n  "source": "DeskSearch",\n  "timestamp": "2025-01-01T12:00:00Z",\n  "total_documents": 1234\n}`} />
      </div>
    </SectionCard>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

interface IntegrationsPanelProps {
  apiKey: string | null | undefined;
  webhookUrls: string[];
  slackWebhookUrl: string | null | undefined;
  port: number;
  onApiKeyChange: (k: string | null) => void;
  onWebhookUrlsChange: (urls: string[]) => void;
  onSlackUrlChange: (url: string | null) => void;
}

export default function IntegrationsPanel({
  apiKey, webhookUrls, slackWebhookUrl, port,
  onApiKeyChange, onWebhookUrlsChange, onSlackUrlChange,
}: IntegrationsPanelProps) {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('integrations.title')}</h3>
        <span className="text-[11px] text-gray-400 bg-gray-100 dark:bg-dark-hover px-2 py-0.5 rounded-full">
          {t('integrations.allOptional')}
        </span>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('integrations.description')}
      </p>

      <ApiKeyCard apiKey={apiKey} port={port} onUpdated={onApiKeyChange} />
      <AlfredCard port={port} apiKey={apiKey} />
      <SlackCard port={port} slackWebhookUrl={slackWebhookUrl} onSaved={onSlackUrlChange} />
      <BrowserBookmarksCard />
      <EmailImportCard />
      <WebhooksCard webhookUrls={webhookUrls} onUpdated={onWebhookUrlsChange} />
    </div>
  );
}
