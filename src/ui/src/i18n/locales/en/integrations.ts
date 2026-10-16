/**
 * integrations namespace (en).
 *
 * Flat { key: string } map; the `integrations.` prefix is added automatically by
 * locales/index.ts, so components call `t('integrations.<key>')`.
 *
 * Note: a few keys are intentionally identical to their zh counterparts
 * (product names, file extensions, technical labels, URL examples).
 */
export default {
  // ── Panel ─────────────────────────────────────────────────────────────────
  'title': 'Integrations',
  'allOptional': 'All optional',
  'description':
    'Connect DeskSearch to external tools. Everything here is optional and has zero impact if not configured.',
  'badge.notConfigured': 'Not configured',
  'or': 'or',
  'saved': 'Saved',
  'saveFailed': 'Failed to save',
  'networkError': 'Network error',
  'errors': '({count} errors)',
  'errors_one': '({count} error)',
  'errors_other': '({count} errors)',

  // ── Setup guides (shared by the Alfred and Slack cards) ────────────────────
  'setup.hideGuide': 'Hide setup guide',
  'setup.showGuide': 'Setup guide',
  'setup.showFullGuide': 'Full setup guide',

  // ── 1. API Key ────────────────────────────────────────────────────────────
  'apiKey.title': 'API Key',
  'apiKey.badge.protected': 'Protected',
  'apiKey.badge.open': 'Open access',
  'apiKey.descBefore': 'Protect',
  'apiKey.descAfter':
    'and other integration endpoints with a bearer token. Leave empty for open access (local-only is fine).',
  'apiKey.hide': 'Hide key',
  'apiKey.show': 'Show key',
  'apiKey.copyKey': 'Copy key',
  'apiKey.copyHeader': 'Copy header',
  'apiKey.empty': 'No API key set — all integration endpoints are open',
  'apiKey.msgGenerated': 'New API key generated',
  'apiKey.msgRegenFailed': 'Failed to regenerate key',
  'apiKey.msgRemoved': 'API key removed — endpoints are now open',
  'apiKey.msgClearFailed': 'Failed to clear key',
  'apiKey.generating': 'Generating…',
  'apiKey.regenerate': 'Regenerate',
  'apiKey.generate': 'Generate API Key',
  'apiKey.removeKey': 'Remove key',
  'apiKey.usageInCurl': 'Usage in curl:',

  // ── 2. Alfred / Raycast ───────────────────────────────────────────────────
  'alfred.title': 'Alfred / Raycast',
  'alfred.badge': 'Always ready',
  'alfred.description':
    'Search DeskSearch from Alfred or Raycast. Point a Script Filter at the endpoint below — it returns Alfred-native JSON.',
  'alfred.scriptFilterUrl': 'Script Filter URL',
  'alfred.termScriptFilter': 'Script Filter',
  'alfred.step1': 'Open Alfred → Workflows → create a new blank workflow.',
  'alfred.step2Add': 'Add a',
  'alfred.step2SetLanguage': 'input. Set Language to',
  'alfred.step2ScriptTo': ', Script to:',
  'alfred.workflowTitle': 'Alfred Workflow',
  'alfred.termOpenFile': 'Open File',
  'alfred.step3Add': 'Add an',
  'alfred.step3Rest': 'output connected to the Script Filter. Done!',
  'alfred.raycastTitle': 'Raycast Script Command',
  'alfred.raycastStep1': 'Create a new Script Command in Raycast.',
  'alfred.raycastStep2': 'Use this script:',
  'alfred.testFromTerminal': 'Test from terminal',

  // ── 3. Slack ──────────────────────────────────────────────────────────────
  'slack.title': 'Slack',
  'slack.descBefore': 'Add a',
  'slack.descAfter': 'slash command to Slack. Your team can search DeskSearch without leaving Slack.',
  'slack.requestUrlLabel': 'Slash Command Request URL',
  'slack.requestUrlHint': '↑ Paste this as the Request URL when creating your Slack slash command.',
  'slack.step1Before': 'Go to',
  'slack.step1After': 'and create a new app.',
  'slack.step2Click': 'Click',
  'slack.step2SlashCommands': 'Slash Commands',
  'slack.step2Arrow': '→',
  'slack.step2CreateNewCommand': 'Create New Command',
  'slack.step2SetCommand': '. Set Command to',
  'slack.step2End': '.',
  'slack.step3':
    'Paste the Request URL above. Make sure DeskSearch is reachable from the internet (use ngrok or Cloudflare Tunnel for local dev).',
  'slack.step4Before': 'Install the app to your workspace. Now',
  'slack.step4After': 'will return results from DeskSearch in any channel.',
  'slack.outgoingWebhook': 'Optional: Outgoing webhook URL (for DeskSearch to POST notifications to Slack)',
  'slack.webhookPlaceholder': 'https://hooks.slack.com/services/...',
  'slack.saveWebhook': 'Save webhook URL',

  // ── 4. Browser Bookmarks ──────────────────────────────────────────────────
  'bookmarks.title': 'Browser Bookmarks',
  'bookmarks.synced': 'Synced',
  'bookmarks.notSynced': 'Not synced',
  'bookmarks.description':
    'Index Chrome and Firefox bookmarks so you can search them alongside your files. Reads from the default browser profile locations automatically.',
  'bookmarks.chrome': 'Chrome',
  'bookmarks.firefox': 'Firefox',
  'bookmarks.noResults': 'No bookmarks found. Make sure Chrome or Firefox is installed.',
  'bookmarks.indexed': 'Indexed {indexed} of {found} bookmarks',
  'bookmarks.syncFailed': 'Sync failed — check that the backend is running.',
  'bookmarks.syncing': 'Syncing…',
  'bookmarks.sync': 'Sync Bookmarks',
  'bookmarks.lastSync': 'Last sync: {time}',

  // ── 5. Email Import ───────────────────────────────────────────────────────
  'email.title': 'Email Import',
  'email.formats': '.mbox / .eml',
  'email.descBefore': 'Import email exports to make them searchable. Drag a',
  'email.descAfter':
    'file below. Supports exports from Apple Mail, Thunderbird, Gmail Takeout, and more.',
  'email.indexing': 'Indexing emails…',
  'email.dropBefore': 'Drop',
  'email.dropAfter': 'here, or',
  'email.browse': 'click to browse',
  'email.onlyMboxEml': 'Only .mbox and .eml files are supported',
  'email.uploadFailed': 'Upload failed',
  'email.uploadFailedBackend': 'Upload failed — check that the backend is running',
  'email.indexed': '— {indexed} of {found} emails indexed',

  // ── 6. Webhooks ───────────────────────────────────────────────────────────
  'webhooks.title': 'Webhook Notifications',
  'webhooks.noneSet': 'None set',
  'webhooks.count': '{count} URLs',
  'webhooks.count_one': '{count} URL',
  'webhooks.count_other': '{count} URLs',
  'webhooks.description':
    'DeskSearch will POST a JSON event to these URLs when indexing completes or new files are found. Useful for triggering CI pipelines, Zapier, or custom automations.',
  'webhooks.testing': 'testing',
  'webhooks.test': 'Test',
  'webhooks.testFailed': '✗ failed',
  'webhooks.urlPlaceholder': 'https://example.com/webhook',
  'webhooks.payloadLabel': 'Example payload sent on indexing_complete:',
} as const;
