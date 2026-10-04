// Preview helpers for the manual configuration page.
// Mirrors frontend/manual/assets/ccswitch-setup-core.js so the preview shows exactly what the manual will do.

export type Client = 'claude' | 'codex' | 'workbuddy'
export type Role = 'fable' | 'opus' | 'sonnet' | 'haiku' | 'subagent'

export interface ClientRules {
  include: string[]
  exclude: string[]
  recommend: string[]
}

export const CLIENTS: { key: Client; label: string; hint: string }[] = [
  { key: 'claude', label: 'Claude Code', hint: 'Anthropic 风格的 Key' },
  { key: 'codex', label: 'Codex', hint: 'OpenAI 风格的 Key' },
  { key: 'workbuddy', label: 'WorkBuddy', hint: 'OpenAI 风格的 Key' },
]

export const ROLES: { key: Role; label: string; hint: string }[] = [
  { key: 'fable', label: 'Fable', hint: '最强，处理最难的任务' },
  { key: 'opus', label: 'Opus', hint: '复杂任务和规划' },
  { key: 'sonnet', label: 'Sonnet', hint: '日常编码主力' },
  { key: 'haiku', label: 'Haiku', hint: '快速小任务和后台任务' },
  { key: 'subagent', label: '子代理', hint: '留空表示跟随 Claude Code 默认' },
]

export const PATTERN_RE = /^[A-Za-z0-9.*_:/-]{1,128}$/
const MODEL_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/

const cache = new Map<string, RegExp>()
export function wildcard(pattern: string): RegExp {
  let re = cache.get(pattern)
  if (!re) {
    const source = pattern.split('*').map((part) => part.replace(/[.+?^${}()|[\]\\/]/g, '\\$&')).join('.*')
    re = new RegExp(`^${source}$`, 'i')
    cache.set(pattern, re)
  }
  return re
}

const matchesAny = (id: string, patterns: string[]) => patterns.some((p) => wildcard(p).test(id))

export function filterModels(ids: string[], rules: ClientRules): string[] {
  const seen = new Set<string>()
  return ids.filter((id) => {
    if (!MODEL_ID_RE.test(id) || seen.has(id)) return false
    seen.add(id)
    return matchesAny(id, rules.include) && !matchesAny(id, rules.exclude)
  })
}

export function newestMatch(ids: string[], pattern: string): string {
  return ids.filter((id) => wildcard(pattern).test(id)).sort((a, b) => b.localeCompare(a, 'en', { numeric: true }))[0] || ''
}

export function firstMatch(ids: string[], patterns: string[]): string {
  for (const pattern of patterns) {
    const match = newestMatch(ids, pattern)
    if (match) return match
  }
  return ''
}

export function recommend(ids: string[], rules: ClientRules): string {
  return firstMatch(ids, rules.recommend) || ids[0] || ''
}

export function suggestRoles(ids: string[], main: string, roles: Record<Role, string[]>): Record<Role, string> {
  return {
    fable: firstMatch(ids, roles.fable) || main,
    opus: firstMatch(ids, roles.opus) || main,
    sonnet: firstMatch(ids, roles.sonnet) || main,
    haiku: firstMatch(ids, roles.haiku) || main,
    subagent: firstMatch(ids, roles.subagent),
  }
}

// Leaf-level differences between two configs, for the version comparison view.
export function diffConfig(before: unknown, after: unknown, path = ''): { path: string; before: string; after: string }[] {
  const show = (v: unknown) => (v === undefined ? '（无）' : typeof v === 'string' ? v : JSON.stringify(v))
  const isObj = (v: unknown) => v !== null && typeof v === 'object' && !Array.isArray(v)
  if (isObj(before) && isObj(after)) {
    const keys = new Set([...Object.keys(before as object), ...Object.keys(after as object)])
    return [...keys].flatMap((key) =>
      diffConfig((before as any)[key], (after as any)[key], path ? `${path}.${key}` : key),
    )
  }
  return JSON.stringify(before) === JSON.stringify(after) ? [] : [{ path, before: show(before), after: show(after) }]
}

export const FIELD_LABELS: Record<string, string> = {
  announcement: '公告',
  install: '安装来源',
  'ccswitch.windows': 'CC Switch 下载来源',
  'claude_roles': 'Claude 角色',
  updated_on: '手册更新时间',
  'site.url': '站点地址',
  'contact.qq': '客服 QQ',
  'announcement.enabled': '公告开关',
  'announcement.level': '公告样式',
  'announcement.text': '公告内容',
  'models.claude.include': 'Claude Code 可用模型',
  'models.claude.exclude': 'Claude Code 排除模型',
  'models.claude.recommend': 'Claude Code 推荐顺序',
  'models.codex.include': 'Codex 可用模型',
  'models.codex.exclude': 'Codex 排除模型',
  'models.codex.recommend': 'Codex 推荐顺序',
  'models.workbuddy.include': 'WorkBuddy 可用模型',
  'models.workbuddy.exclude': 'WorkBuddy 排除模型',
  'models.workbuddy.recommend': 'WorkBuddy 推荐顺序',
  'claude_roles.fable': 'Fable 角色',
  'claude_roles.opus': 'Opus 角色',
  'claude_roles.sonnet': 'Sonnet 角色',
  'claude_roles.haiku': 'Haiku 角色',
  'claude_roles.subagent': '子代理',
  'workbuddy.max_input_tokens': 'WorkBuddy 输入上限',
  'workbuddy.max_output_tokens': 'WorkBuddy 输出上限',
  'workbuddy.supports_tool_call': 'WorkBuddy 工具调用',
  'workbuddy.supports_images': 'WorkBuddy 图片输入',
  'workbuddy.supports_reasoning': 'WorkBuddy 思考模式',
  'install.npm_registry': 'npm 国内镜像',
  'install.npm_registry_fallback': 'npm 备用源',
  'install.node_mirror': 'Node.js 下载镜像',
  'install.node_min_major': 'Node.js 最低版本',
  'install.node_lts_major': 'Node.js 安装版本',
  'install.claude_package': 'Claude Code npm 包',
  'install.codex_package': 'Codex npm 包',
  'install.codex_store_id': 'Codex 微软商店 ID',
  'install.workbuddy_winget_id': 'WorkBuddy winget ID',
  'install.workbuddy_site': 'WorkBuddy 官网',
  'install.workbuddy_size_mb': 'WorkBuddy 安装包大小',
  'ccswitch.version': 'CC Switch 版本',
  'ccswitch.windows.source': 'CC Switch 下载来源',
  'ccswitch.windows.file_id': 'CC Switch 上传文件',
  'ccswitch.windows.url': 'CC Switch 下载地址',
  'ccswitch.releases_url': 'CC Switch 发布页',
}
