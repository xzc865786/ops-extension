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
  // Lists of objects (groups, FAQ) are compared entry by entry; lists of model IDs stay one row.
  const objList = (v: unknown) => Array.isArray(v) && v.every(isObj)
  if (objList(before) && objList(after)) {
    const a = before as any[], b = after as any[]
    // An added or removed entry is shown by its name (group) or question (FAQ), not as raw JSON.
    const brief = (v: any) => (v === undefined ? '（无）' : String(v.name ?? v.q ?? JSON.stringify(v)))
    return Array.from({ length: Math.max(a.length, b.length) }, (_, i) =>
      a[i] === undefined || b[i] === undefined
        ? [{ path: `${path}.${i}`, before: brief(a[i]), after: brief(b[i]) }]
        : diffConfig(a[i], b[i], `${path}.${i}`),
    ).flat()
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
  'contact.qq': '客服 QQ 群',
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

const GROUP_FIELD_LABELS: Record<string, string> = {
  name: '名称',
  sub2api_id: 'Sub2API 编号',
  visible: '在手册显示',
  platform: 'Key 风格',
  clients: '适用软件',
  badge: '标签',
  rate_multiplier: '倍率',
  billing_note: '倍率说明',
  summary: '一句话介绍',
  suitable_for: '适合',
  models: '主要模型',
  notes: '注意事项',
  q: '问题',
  a: '回答',
}

FIELD_LABELS.groups = '分组说明'
FIELD_LABELS['groups.intro'] = '分组页开头说明'
FIELD_LABELS['groups.notice'] = '分组页提示'
FIELD_LABELS['groups.items'] = '分组列表'
FIELD_LABELS['groups.faq'] = '分组常见问题'

// Chinese name for a config path, including list entries such as groups.items.2.models.0.
export function fieldLabel(path: string): string | undefined {
  const entry = path.match(/^groups\.(items|faq)\.(\d+)(?:\.([a-z_]+))?/)
  if (entry) {
    const owner = entry[1] === 'items' ? `第 ${Number(entry[2]) + 1} 个分组` : `第 ${Number(entry[2]) + 1} 条常见问题`
    return entry[3] ? `${owner} · ${GROUP_FIELD_LABELS[entry[3]] || entry[3]}` : owner
  }
  return FIELD_LABELS[path.replace(/\.\d+$/, '')]
}

// ---- Groups ----------------------------------------------------------------

export type GroupClient = Client
export type GroupBadge = '' | 'recommended' | 'stable' | 'value' | 'limited' | 'exclusive'

export interface GroupInfo {
  name: string
  sub2api_id: number | null
  visible: boolean
  platform: string
  clients: GroupClient[]
  badge: GroupBadge
  rate_multiplier: number | null
  billing_note: string
  summary: string
  suitable_for: string[]
  models: string[]
  notes: string
}

export interface GroupsConfig {
  intro: string
  notice: string
  items: GroupInfo[]
  faq: { q: string; a: string }[]
}

export interface Sub2APIGroup {
  id: number
  name: string
  description: string
  platform: string
  status: string
  rate_multiplier: number | null
  is_exclusive: boolean
  subscription_type: string
  allow_messages_dispatch: boolean
  claude_code_only: boolean
  peak: { start: string; end: string; multiplier: number } | null
  models: string[]
}

export const GROUP_BADGES: { key: GroupBadge; label: string }[] = [
  { key: '', label: '无' },
  { key: 'recommended', label: '推荐' },
  { key: 'stable', label: '稳定' },
  { key: 'value', label: '实惠' },
  { key: 'limited', label: '限时' },
  { key: 'exclusive', label: '专属' },
]

export const PLATFORM_LABELS: Record<string, string> = { anthropic: 'Anthropic', openai: 'OpenAI', gemini: 'Gemini' }

export function emptyGroup(): GroupInfo {
  return {
    name: '', sub2api_id: null, visible: true, platform: '', clients: [], badge: '', rate_multiplier: null,
    billing_note: '', summary: '', suitable_for: [], models: [], notes: '',
  }
}

export function clientsForPlatform(group: Pick<Sub2APIGroup, 'platform' | 'claude_code_only'>): GroupClient[] {
  if (group.claude_code_only || group.platform === 'anthropic') return ['claude']
  if (group.platform === 'openai') return ['codex', 'workbuddy']
  return []
}

export function groupFromSub2API(group: Sub2APIGroup): GroupInfo {
  const peak = group.peak ? `高峰时段 ${group.peak.start}–${group.peak.end} 倍率 ${group.peak.multiplier}×` : ''
  return {
    ...emptyGroup(),
    name: group.name,
    sub2api_id: group.id,
    platform: /^[a-z0-9_]{1,32}$/.test(group.platform) ? group.platform : '',
    clients: clientsForPlatform(group),
    badge: group.is_exclusive ? 'exclusive' : '',
    rate_multiplier: group.rate_multiplier,
    billing_note: peak,
    summary: group.description.slice(0, 200),
    models: group.models.filter((m) => PATTERN_RE.test(m)).slice(0, 30),
  }
}

// The manual entry for a Sub2API group: same id, or same name for entries typed in by hand.
export function findGroup(items: GroupInfo[], group: Sub2APIGroup): GroupInfo | undefined {
  return items.find((item) => item.sub2api_id === group.id) || items.find((item) => !item.sub2api_id && item.name === group.name)
}

// What would change if the manual entry were synced with Sub2API; empty when it is up to date.
export function groupChanges(item: GroupInfo, group: Sub2APIGroup): string[] {
  const changes: string[] = []
  if (item.name !== group.name) changes.push(`名称 ${item.name} → ${group.name}`)
  if (item.rate_multiplier !== group.rate_multiplier) {
    changes.push(`倍率 ${item.rate_multiplier ?? '未填'} → ${group.rate_multiplier ?? '未填'}`)
  }
  if (group.platform && item.platform !== group.platform) changes.push(`风格 ${item.platform || '未填'} → ${group.platform}`)
  if (item.sub2api_id !== group.id) changes.push('关联 Sub2API 分组')
  return changes
}

// Sync keeps everything the admin wrote; only the facts Sub2API owns are overwritten.
export function syncGroup(item: GroupInfo, group: Sub2APIGroup): void {
  item.name = group.name
  item.sub2api_id = group.id
  item.rate_multiplier = group.rate_multiplier
  if (/^[a-z0-9_]{1,32}$/.test(group.platform)) item.platform = group.platform
  if (!item.models.length) item.models = group.models.filter((m) => PATTERN_RE.test(m)).slice(0, 30)
}

