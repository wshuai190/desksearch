/**
 * `search` 命名空间（中文）—— 搜索框、首屏、快捷统计、提示、示例查询。
 */
export default {
  // 输入框
  'placeholder': '搜索你的文件…',
  'placeholderListening': '正在聆听…',
  'voiceSearch': '语音搜索',
  'voiceUnsupported': '当前浏览器不支持语音搜索。',
  'clearTitle': '清空（Esc）',
  'clearLabel': '清空搜索',
  'recentSearches': '最近搜索',
  'removeRecent': '移除',

  // 首屏
  'subtitleCount': '在 {count} 个文件中按语义搜索',
  'subtitleGeneric': '按语义搜索文件，而不只是关键词',
  'indexing': '正在读取你的文件…现在也可以直接开始搜索！',
  'noFilesTitle': '尚未索引任何文件',
  'noFilesHint': '前往「{tab}」添加一个文件夹即可开始。',
  'trySearching': '试试搜索',
  'kbdHintBefore': '随时按',
  'kbdHintOr': '或',
  'kbdHintAfter': '聚焦搜索框',

  // 快捷统计
  'stats.filesIndexed': '已索引文件',
  'stats.lastUpdated': '最近更新',
  'stats.indexSize': '索引大小',
  'time.never': '从未',
  'time.justNow': '刚刚',
  'time.minutesAgo': '{count} 分钟前',
  'time.hoursAgo': '{count} 小时前',

  // 提示
  'tips.meaning': '按语义搜索，而不只是关键词',
  'tips.filters': '按日期、文件类型或文件夹筛选',
  'tips.voice': '使用语音搜索，或按 / 聚焦输入框',

  // 轮换展示的示例查询（每次取 3 条）
  'examples.0': '上个月的会议记录',
  'examples.1': '项目预算表格',
  'examples.2': '来自某公司的发票',
  'examples.3': '处理数据的 Python 脚本',
  'examples.4': '关于季度复盘的笔记',
  'examples.5': '2023 年签署的合同',
  'examples.6': '关于会议的邮件',
  'examples.7': '项目的待办清单',
} as const;
