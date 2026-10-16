/**
 * results 命名空间（中文）。
 *
 * 扁平 { key: string } 映射；`results.` 前缀由 locales/index.ts 自动添加，
 * 因此组件里写 `t('results.<key>')`。
 *
 * 通用词（打开、预览、复制、加载中、结果数量……）已在 `common.ts` 中定义，
 * 请直接复用，不要在这里重复翻译。
 */
export default {
  // 结果数量 + 查询耗时
  'countLabel': '{count} 条结果',
  'countLabel_one': '{count} 条结果',
  'timeMs': '{ms} 毫秒',
  'timeSeconds': '{seconds} 秒',

  // 排序选项
  'sortRelevance': '相关度',
  'sortDateNewest': '日期（最新）',
  'sortDateOldest': '日期（最早）',
  'sortSizeLargest': '大小（最大）',
  'sortSizeSmallest': '大小（最小）',
  'sortFileType': '文件类型',

  // 键盘导航提示
  'hintNavigate': '切换结果',
  'hintNextResult': '下一个结果',
  'hintNewSearch': '重新搜索',

  // 空结果状态
  'emptyTitle': '没有找到与“{query}”相关的结果',
  'emptyBody': '换个说法描述你的文件试试。DeskSearch 能理解语义，换一种表达方式也许就能找到了。',
  'searchTips': '搜索技巧',
  'tip1': '试着描述文件的内容，例如“项目预算表格”',
  'tip2': '使用自然语言，例如“上个月的会议记录”',
  'tip3': '按内容搜索，而不是按文件名 —— 例如“Acme 公司的发票”',
  'tip4': '放宽搜索范围 —— 去掉具体的日期或名称',
  'newSearch': '换一个关键词搜索',

  // 错误状态
  'errorTitleServer': '连不上 DeskSearch',
  'errorTitleGeneric': '出了点问题',
  'errorBodyServer': '请确认 DeskSearch 应用正在运行，然后再试一次。',
  'errorBodyGeneric': '请刷新页面重试。如果问题反复出现，请重启 DeskSearch。',
  'refreshPage': '刷新页面',

  // 相关度 / 匹配评分
  'scoreExcellent': '极佳',
  'scoreGood': '良好',
  'scorePartial': '部分匹配',

  // 相对时间
  'daysAgo': '{count} 天前',
  'weeksAgo': '{count} 周前',

  // 结果卡片操作 + 关联文档
  'copied': '已复制',
  'copyPath': '复制路径',
  'quickPreview': '快速预览',
  'similar': '相似文档',
  'similarTitle': '{filename}（相似度 {percent}%）',

  // 文档预览面板
  'previewUnavailable': '无法预览',
  'statSize': '大小',
  'statWords': '字数',
  'statChunks': '片段数',
  'lastModified': '最后修改：',
  'keyTopics': '关键主题',
  'contentPreview': '内容预览',
  'closeEsc': '关闭（Esc）',

  // 状态栏
  'updatedJustNow': '刚刚更新',
  'updatedMinutesAgo': '{count} 分钟前更新',
  'updatedHoursAgo': '{count} 小时前更新',
  'updatedOn': '更新于 {date}',
  'notRunning': 'DeskSearch 未运行',
  'notRunningHint': '—— 请打开 DeskSearch 应用后重试',
  'readingFiles': '正在读取文件…',
  'readingYourFiles': '正在读取你的文件…',
  'filesReady': '{count} 个文件已就绪',
  'filesReady_one': '{count} 个文件已就绪',
  'filesReadyLabel': '个文件已就绪',
  'filesReadyLabel_one': '个文件已就绪',
  'doneSoFar': '已完成 {count} 个',
  'doneCount': '已完成 {count} 个',
  'noFilesIndexed': '还没有建立索引',
  'noFilesIndexedHint': '还没有建立索引 —— 添加文件夹即可开始',
} as const;
