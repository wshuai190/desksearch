/**
 * integrations 命名空间（zh）。
 *
 * 这里是扁平的 { key: string } 映射，`integrations.` 前缀由 locales/index.ts
 * 自动添加，因此组件里写 `t('integrations.<key>')`。
 *
 * 注意：部分 key 与英文完全一致（产品名、文件扩展名、技术标签、URL 示例），
 * 属于有意保留的英文术语。
 */
export default {
  // ── 面板 ──────────────────────────────────────────────────────────────────
  'title': '集成',
  'allOptional': '全部可选',
  'description': '把 DeskSearch 连接到外部工具。以下配置全部可选，不配置也不会有任何影响。',
  'badge.notConfigured': '未配置',
  'or': '或',
  'saved': '已保存',
  'saveFailed': '保存失败',
  'networkError': '网络错误',
  'errors': '（{count} 个错误）',
  'errors_one': '（{count} 个错误）',
  'errors_other': '（{count} 个错误）',

  // ── 配置指南（Alfred 与 Slack 卡片共用）──────────────────────────────────
  'setup.hideGuide': '收起配置指南',
  'setup.showGuide': '配置指南',
  'setup.showFullGuide': '完整配置指南',

  // ── 1. API 密钥 ───────────────────────────────────────────────────────────
  'apiKey.title': 'API 密钥',
  'apiKey.badge.protected': '受保护',
  'apiKey.badge.open': '开放访问',
  'apiKey.descBefore': '使用 Bearer Token 保护',
  'apiKey.descAfter': '及其他集成接口。留空则为开放访问（仅本机使用没有问题）。',
  'apiKey.hide': '隐藏密钥',
  'apiKey.show': '显示密钥',
  'apiKey.copyKey': '复制密钥',
  'apiKey.copyHeader': '复制请求头',
  'apiKey.empty': '未设置 API 密钥——所有集成接口均处于开放状态',
  'apiKey.msgGenerated': '已生成新的 API 密钥',
  'apiKey.msgRegenFailed': '重新生成密钥失败',
  'apiKey.msgRemoved': 'API 密钥已移除——接口现在处于开放状态',
  'apiKey.msgClearFailed': '清除密钥失败',
  'apiKey.generating': '生成中…',
  'apiKey.regenerate': '重新生成',
  'apiKey.generate': '生成 API 密钥',
  'apiKey.removeKey': '移除密钥',
  'apiKey.usageInCurl': '在 curl 中的用法：',

  // ── 2. Alfred / Raycast ───────────────────────────────────────────────────
  'alfred.title': 'Alfred / Raycast',
  'alfred.badge': '始终可用',
  'alfred.description':
    '在 Alfred 或 Raycast 中直接搜索 DeskSearch。把 Script Filter 指向下面的接口，它会返回 Alfred 原生格式的 JSON。',
  'alfred.scriptFilterUrl': 'Script Filter URL',
  'alfred.termScriptFilter': 'Script Filter',
  'alfred.step1': '打开 Alfred → Workflows → 新建一个空白 workflow。',
  'alfred.step2Add': '添加一个',
  'alfred.step2SetLanguage': '输入，Language 选择',
  'alfred.step2ScriptTo': '，Script 填：',
  'alfred.workflowTitle': 'Alfred Workflow',
  'alfred.termOpenFile': 'Open File',
  'alfred.step3Add': '添加一个',
  'alfred.step3Rest': '输出，连接到刚才的 Script Filter 即可。',
  'alfred.raycastTitle': 'Raycast Script Command',
  'alfred.raycastStep1': '在 Raycast 中新建一个 Script Command。',
  'alfred.raycastStep2': '使用下面的脚本：',
  'alfred.testFromTerminal': '在终端中测试',

  // ── 3. Slack ──────────────────────────────────────────────────────────────
  'slack.title': 'Slack',
  'slack.descBefore': '为 Slack 添加一个',
  'slack.descAfter': '斜杠命令，团队成员无需离开 Slack 即可搜索 DeskSearch。',
  'slack.requestUrlLabel': '斜杠命令 Request URL',
  'slack.requestUrlHint': '↑ 创建 Slack 斜杠命令时，把这里的内容粘贴到 Request URL。',
  'slack.step1Before': '前往',
  'slack.step1After': '，创建一个新应用。',
  'slack.step2Click': '点击',
  'slack.step2SlashCommands': 'Slash Commands',
  'slack.step2Arrow': '→',
  'slack.step2CreateNewCommand': 'Create New Command',
  'slack.step2SetCommand': '，将 Command 设为',
  'slack.step2End': '。',
  'slack.step3':
    '把上面的 Request URL 粘贴进去。请确保 DeskSearch 能从公网访问（本地开发可以使用 ngrok 或 Cloudflare Tunnel）。',
  'slack.step4Before': '把应用安装到你的工作区。之后在任意频道输入',
  'slack.step4After': '即可返回 DeskSearch 的搜索结果。',
  'slack.outgoingWebhook': '可选：出站 webhook URL（用于 DeskSearch 向 Slack 推送通知）',
  'slack.webhookPlaceholder': 'https://hooks.slack.com/services/...',
  'slack.saveWebhook': '保存 webhook URL',

  // ── 4. 浏览器书签 ─────────────────────────────────────────────────────────
  'bookmarks.title': '浏览器书签',
  'bookmarks.synced': '已同步',
  'bookmarks.notSynced': '未同步',
  'bookmarks.description':
    '索引 Chrome 和 Firefox 的书签，让它们可以和文件一起被搜索。会自动读取浏览器默认配置目录。',
  'bookmarks.chrome': 'Chrome',
  'bookmarks.firefox': 'Firefox',
  'bookmarks.noResults': '未找到书签。请确认已安装 Chrome 或 Firefox。',
  'bookmarks.indexed': '已索引 {indexed}/{found} 个书签',
  'bookmarks.syncFailed': '同步失败——请检查后端是否在运行。',
  'bookmarks.syncing': '同步中…',
  'bookmarks.sync': '同步书签',
  'bookmarks.lastSync': '上次同步：{time}',

  // ── 5. 邮件导入 ───────────────────────────────────────────────────────────
  'email.title': '邮件导入',
  'email.formats': '.mbox / .eml',
  'email.descBefore': '导入邮件导出文件，让它们可以被搜索。把',
  'email.descAfter': '文件拖到下方即可。支持 Apple Mail、Thunderbird、Gmail Takeout 等导出的邮件。',
  'email.indexing': '正在索引邮件…',
  'email.dropBefore': '将',
  'email.dropAfter': '拖到这里，或',
  'email.browse': '点击选择文件',
  'email.onlyMboxEml': '仅支持 .mbox 和 .eml 文件',
  'email.uploadFailed': '上传失败',
  'email.uploadFailedBackend': '上传失败——请检查后端是否在运行',
  'email.indexed': '— 已索引 {indexed}/{found} 封邮件',

  // ── 6. Webhook ────────────────────────────────────────────────────────────
  'webhooks.title': 'Webhook 通知',
  'webhooks.noneSet': '未设置',
  'webhooks.count': '{count} 个 URL',
  'webhooks.count_one': '{count} 个 URL',
  'webhooks.count_other': '{count} 个 URL',
  'webhooks.description':
    '当索引完成或发现新文件时，DeskSearch 会向这些 URL 发送一个 JSON 事件。可用于触发 CI 流水线、Zapier 或自定义自动化。',
  'webhooks.testing': '测试中',
  'webhooks.test': '测试',
  'webhooks.testFailed': '✗ 失败',
  'webhooks.urlPlaceholder': 'https://example.com/webhook',
  'webhooks.payloadLabel': 'indexing_complete 时发送的示例负载：',
} as const;
