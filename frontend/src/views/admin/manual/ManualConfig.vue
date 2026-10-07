<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import api from '@/api/client'
import ManualGroupsEditor from '@/components/ManualGroupsEditor.vue'
import PatternList from '@/components/PatternList.vue'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/display'
import {
  CLIENTS, ROLES, diffConfig, fieldLabel, filterModels, recommend, suggestRoles,
  type Client, type Role,
} from '@/utils/manualRules'

type Tab = 'basic' | 'models' | 'roles' | 'clients' | 'ccswitch' | 'groups' | 'preview' | 'history'
const TABS: { key: Tab; label: string }[] = [
  { key: 'basic', label: '基本信息' },
  { key: 'models', label: '推荐模型' },
  { key: 'roles', label: 'Claude 角色' },
  { key: 'clients', label: '安装与客户端' },
  { key: 'ccswitch', label: 'CC Switch 下载' },
  { key: 'groups', label: '分组说明' },
  { key: 'preview', label: '预览' },
  { key: 'history', label: '版本历史' },
]

const toast = useToast()
const tab = ref<Tab>('basic')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const live = ref<any>(null)
const defaults = ref<any>(null)
const form = ref<any>(null)
const note = ref('')
const touchDate = ref(true)
const files = ref<any[]>([])
const versions = ref<any[]>([])

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const dirty = computed(() => !!form.value && JSON.stringify(form.value) !== JSON.stringify(live.value?.config))
const site = computed(() => (form.value?.site.url || '').replace(/\/+$/, ''))
const endpoints = computed(() => ({
  claude: site.value,
  codex: `${site.value}/v1`,
  workbuddy: `${site.value}/v1/chat/completions`,
}))

function errMsg(e: any, fallback: string) {
  const data = e.response?.data
  const message: string = data?.detail?.detail || (typeof data?.detail === 'string' ? data.detail : '') || fallback
  // Validation errors come back as "path：message"; show the field's Chinese name instead of the path.
  return message.split('；').map((part) => {
    const [path, ...rest] = part.split('：')
    const label = fieldLabel(path.replace(/^config\./, ''))
    return rest.length && label ? `${label}：${rest.join('：')}` : part
  }).join('；')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [config, fileList, versionList] = await Promise.all([
      api.get('/admin/manual/config'),
      api.get('/admin/manual/files'),
      api.get('/admin/manual/versions'),
    ])
    live.value = config.data
    defaults.value = config.data.defaults
    form.value = clone(config.data.config)
    files.value = fileList.data
    versions.value = versionList.data
  } catch (e: any) {
    error.value = errMsg(e, '加载手册配置失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function save() {
  if (!form.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api.put('/admin/manual/config', {
      config: form.value,
      base_version: live.value.version,
      note: note.value.trim() || null,
      touch_updated_on: touchDate.value,
    })
    note.value = ''
    await load()
    toast.success(`已保存为版本 ${live.value.version}，手册 1 分钟内生效`)
  } catch (e: any) {
    error.value = errMsg(e, '保存失败')
    toast.error(error.value)
  } finally {
    saving.value = false
  }
}

function discard() {
  form.value = clone(live.value.config)
  error.value = ''
}

function loadDefaults() {
  if (!confirm('把分组说明以外的配置改回初始默认值？需要点“保存”才会生效。')) return
  form.value = { ...clone(defaults.value), updated_on: form.value.updated_on, groups: form.value.groups }
  toast.push('已载入默认值，确认无误后点“保存”')
}

// ---- files ---------------------------------------------------------------
const fileInput = ref<HTMLInputElement | null>(null)
const fileDescription = ref('')
const uploading = ref(false)

function formatSize(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
}

async function upload() {
  const file = fileInput.value?.files?.[0]
  if (!file) {
    toast.error('请先选择文件')
    return
  }
  uploading.value = true
  try {
    const body = new FormData()
    body.append('file', file)
    if (fileDescription.value.trim()) body.append('description', fileDescription.value.trim())
    const { data } = await api.post('/admin/manual/files', body)
    files.value = [data, ...files.value]
    fileDescription.value = ''
    if (fileInput.value) fileInput.value.value = ''
    toast.success(`已上传 ${data.file_name}`)
  } catch (e: any) {
    toast.error(errMsg(e, '上传失败'))
  } finally {
    uploading.value = false
  }
}

function useFile(file: any) {
  form.value.ccswitch.windows = { source: 'file', file_id: file.id, url: '' }
  const match = file.file_name.match(/v?(\d+\.\d+\.\d+)/)
  if (match) form.value.ccswitch.version = match[1]
  toast.push('已选为 Windows 下载文件，点“保存”后生效')
}

async function removeFile(file: any) {
  if (!confirm(`删除文件 ${file.file_name}？`)) return
  try {
    await api.delete(`/admin/manual/files/${file.id}`)
    files.value = files.value.filter((f) => f.id !== file.id)
    toast.success('文件已删除')
  } catch (e: any) {
    toast.error(errMsg(e, '删除失败'))
  }
}

const selectedFile = computed(() => files.value.find((f) => f.id === form.value?.ccswitch.windows.file_id))

function setDownloadSource(source: 'url' | 'file') {
  const windows = form.value.ccswitch.windows
  if (source === 'url') form.value.ccswitch.windows = { source: 'url', file_id: null, url: windows.url || defaults.value.ccswitch.windows.url }
  else form.value.ccswitch.windows = { source: 'file', file_id: files.value[0]?.id ?? null, url: '' }
}

// ---- preview -------------------------------------------------------------
const preview = reactive({ mode: 'list' as 'key' | 'list', key: '', list: '', loading: false, ids: [] as string[], error: '' })

async function runPreview() {
  preview.error = ''
  if (preview.mode === 'list') {
    preview.ids = preview.list.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean)
    return
  }
  if (!preview.key.trim()) {
    preview.error = '请粘贴一把 Key'
    return
  }
  preview.loading = true
  try {
    const response = await fetch('/v1/models', {
      headers: { Authorization: `Bearer ${preview.key.trim()}`, Accept: 'application/json' },
      credentials: 'omit',
      cache: 'no-store',
    })
    if (!response.ok) throw new Error(response.status === 401 ? 'Key 无效或已失效' : `读取失败（HTTP ${response.status}）`)
    const body = await response.json()
    preview.ids = (body?.data || []).map((m: any) => String(m?.id || '')).filter(Boolean)
  } catch (e: any) {
    preview.error = e instanceof TypeError ? '无法连接模型接口' : e.message
  } finally {
    preview.loading = false
    preview.key = ''
  }
}

const previewResult = computed(() => {
  if (!form.value || !preview.ids.length) return null
  const result = {} as Record<Client, { models: string[]; recommended: string }>
  for (const client of CLIENTS) {
    const models = filterModels(preview.ids, form.value.models[client.key])
    result[client.key] = { models, recommended: recommend(models, form.value.models[client.key]) }
  }
  const roles = suggestRoles(result.claude.models, result.claude.recommended, form.value.claude_roles)
  return { clients: result, roles }
})

// ---- history -------------------------------------------------------------
const compare = ref<{ version: number; rows: { path: string; before: string; after: string }[] } | null>(null)

async function showDiff(version: number) {
  try {
    const { data } = await api.get(`/admin/manual/versions/${version}`)
    compare.value = { version, rows: diffConfig(data.config, live.value.config) }
  } catch (e: any) {
    toast.error(errMsg(e, '读取版本失败'))
  }
}

async function restore(version: number) {
  if (dirty.value && !confirm('当前有未保存的修改，恢复后这些修改会丢失。继续？')) return
  if (!confirm(`恢复到版本 ${version}？会生成一个新版本，旧版本都保留。`)) return
  try {
    await api.post(`/admin/manual/versions/${version}/restore`, { base_version: live.value.version })
    compare.value = null
    await load()
    toast.success(`已恢复到版本 ${version}（新版本 ${live.value.version}）`)
  } catch (e: any) {
    toast.error(errMsg(e, '恢复失败'))
  }
}

const roleList = (role: Role) => form.value.claude_roles[role] as string[]
</script>

<template>
  <div class="pb-28">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">手册配置</h1>
        <p v-if="live" class="page-subtitle">
          当前版本 {{ live.version }} · {{ live.created_by_name || '系统' }} · {{ formatDateTime(live.created_at) }}
        </p>
      </div>
      <div class="page-toolbar-actions">
        <a class="btn-secondary btn-sm" :href="tab === 'groups' ? '/docs/groups.html' : '/docs/'" target="_blank" rel="noopener">{{ tab === 'groups' ? '打开分组页' : '打开手册' }} ↗</a>
        <button type="button" class="btn-ghost btn-sm" :disabled="!form" @click="loadDefaults">恢复默认值</button>
      </div>
    </div>

    <div v-if="error" class="alert-error mb-4" role="alert">{{ error }}</div>
    <div v-if="loading && !form" class="card p-6 muted">加载中…</div>

    <template v-if="form">
      <div class="tabs mb-4 w-fit max-w-full overflow-x-auto">
        <button v-for="t in TABS" :key="t.key" type="button" class="tab" :class="tab === t.key ? 'tab-active' : ''" @click="tab = t.key">
          {{ t.label }}
        </button>
      </div>

      <!-- 基本信息 -->
      <div v-if="tab === 'basic'" class="space-y-4">
        <section class="card p-5 sm:p-6 space-y-4">
          <h2 class="font-semibold">站点地址</h2>
          <div>
            <label class="input-label" for="site-url">站点根地址（https，不带路径）</label>
            <input id="site-url" v-model.trim="form.site.url" class="input" placeholder="https://api.tysy.top" />
          </div>
          <div class="grid gap-2 text-sm sm:grid-cols-3">
            <div class="rounded-lg bg-slate-50 p-3"><p class="muted text-xs">Claude Code</p><code class="break-all">{{ endpoints.claude }}</code></div>
            <div class="rounded-lg bg-slate-50 p-3"><p class="muted text-xs">Codex</p><code class="break-all">{{ endpoints.codex }}</code></div>
            <div class="rounded-lg bg-slate-50 p-3"><p class="muted text-xs">WorkBuddy</p><code class="break-all">{{ endpoints.workbuddy }}</code></div>
          </div>
          <p class="muted text-xs">控制台链接、参数表、配置脚本和 CC Switch 导入链接都会使用这个地址。</p>
        </section>

        <section class="card p-5 sm:p-6 space-y-4">
          <h2 class="font-semibold">联系方式与更新时间</h2>
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <label class="input-label" for="qq">客服 QQ 群（留空则不显示）</label>
              <input id="qq" v-model.trim="form.contact.qq" class="input" inputmode="numeric" placeholder="1045113768" />
            </div>
            <div>
              <label class="input-label" for="updated-on">手册更新时间</label>
              <input id="updated-on" v-model="form.updated_on" type="date" class="input" :disabled="touchDate" />
              <p class="muted mt-1 text-xs">{{ touchDate ? '保存时会自动改为今天；取消底部的勾选后可以手动修改。' : '将按这里填写的日期显示。' }}</p>
            </div>
          </div>
        </section>

        <section class="card p-5 sm:p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="font-semibold">公告横幅</h2>
            <label class="flex items-center gap-2 text-sm"><input v-model="form.announcement.enabled" type="checkbox" /> 显示公告</label>
          </div>
          <div class="grid gap-4 sm:grid-cols-[160px_minmax(0,1fr)]">
            <div>
              <label class="input-label" for="ann-level">样式</label>
              <select id="ann-level" v-model="form.announcement.level" class="input">
                <option value="info">普通（青色）</option>
                <option value="warning">警告（黄色）</option>
              </select>
            </div>
            <div>
              <label class="input-label" for="ann-text">内容（纯文本，最多 300 字）</label>
              <textarea id="ann-text" v-model="form.announcement.text" class="input" rows="2" maxlength="300" placeholder="例如：gpt-6.1-sol 今晚 22:00–23:00 维护"></textarea>
            </div>
          </div>
          <p class="muted text-xs">公告只显示在手册各页面顶部。</p>
        </section>
      </div>

      <!-- 推荐模型 -->
      <div v-if="tab === 'models'" class="space-y-4">
        <p class="muted text-sm">
          规则用“模型 ID + 通配符”填写，<code>*</code> 代表任意字符，不区分大小写，例如 <code>gpt-6.1-sol</code>、<code>claude-sonnet-*</code>、<code>*codex*</code>。
          读取模型时，先按“可用模型”和“排除模型”过滤，再按“推荐顺序”从上到下找第一个匹配的模型作为默认选中项；同一条规则匹配多个时选版本号最新的。
        </p>
        <section v-for="client in CLIENTS" :key="client.key" class="card p-5 sm:p-6">
          <h2 class="font-semibold">{{ client.label }} <span class="muted text-sm font-normal">· {{ client.hint }}</span></h2>
          <div class="mt-4 grid gap-5 lg:grid-cols-3">
            <div>
              <p class="input-label">可用模型（至少一条）</p>
              <PatternList v-model="form.models[client.key].include" placeholder="例如 gpt* 或 deepseek*" />
            </div>
            <div>
              <p class="input-label">排除模型</p>
              <PatternList v-model="form.models[client.key].exclude" placeholder="例如 *-preview" />
            </div>
            <div>
              <p class="input-label">推荐顺序（从上到下）</p>
              <PatternList v-model="form.models[client.key].recommend" ordered />
            </div>
          </div>
        </section>
      </div>

      <!-- Claude 角色 -->
      <div v-if="tab === 'roles'" class="space-y-4">
        <p class="muted text-sm">
          Claude Code 会按任务调用不同角色的模型。每个角色按列表从上到下找分组里第一个匹配的模型；都找不到时用主模型代替，避免调用不存在的模型而报错。
          子代理留空表示跟随 Claude Code 的默认设置。
        </p>
        <div class="grid gap-4 md:grid-cols-2">
          <section v-for="role in ROLES" :key="role.key" class="card p-5">
            <h2 class="font-semibold">{{ role.label }} <span class="muted text-sm font-normal">· {{ role.hint }}</span></h2>
            <div class="mt-3"><PatternList v-model="form.claude_roles[role.key]" ordered placeholder="例如 *opus*" /></div>
            <p v-if="!roleList(role.key).length && role.key !== 'subagent'" class="mt-2 text-xs text-amber-700">列表为空时直接使用主模型。</p>
          </section>
        </div>
      </div>

      <!-- 安装与客户端 -->
      <div v-if="tab === 'clients'" class="space-y-4">
        <section class="card p-5 sm:p-6 space-y-4">
          <h2 class="font-semibold">安装来源 <span class="muted text-sm font-normal">· 写入用户下载的安装脚本</span></h2>
          <div class="grid gap-4 sm:grid-cols-2">
            <div><label class="input-label">npm 国内镜像</label><input v-model.trim="form.install.npm_registry" class="input" /></div>
            <div><label class="input-label">npm 备用源（国内镜像失败时使用）</label><input v-model.trim="form.install.npm_registry_fallback" class="input" /></div>
            <div class="sm:col-span-2"><label class="input-label">Node.js 下载镜像</label><input v-model.trim="form.install.node_mirror" class="input" /></div>
            <div><label class="input-label">Node.js 最低版本（主版本号）</label><input v-model.number="form.install.node_min_major" type="number" min="18" max="60" class="input" /></div>
            <div><label class="input-label">Node.js 安装版本（LTS 主版本号）</label><input v-model.number="form.install.node_lts_major" type="number" min="18" max="60" class="input" /></div>
            <div><label class="input-label">Claude Code npm 包名</label><input v-model.trim="form.install.claude_package" class="input" /></div>
            <div><label class="input-label">Codex 命令行版 npm 包名</label><input v-model.trim="form.install.codex_package" class="input" /></div>
            <div><label class="input-label">Codex 桌面版微软商店 ID（12 位）</label><input v-model.trim="form.install.codex_store_id" class="input" @blur="form.install.codex_store_id = form.install.codex_store_id.toUpperCase()" /></div>
            <div><label class="input-label">WorkBuddy winget ID</label><input v-model.trim="form.install.workbuddy_winget_id" class="input" /></div>
            <div><label class="input-label">WorkBuddy 官网（winget 失败时打开）</label><input v-model.trim="form.install.workbuddy_site" class="input" /></div>
            <div><label class="input-label">WorkBuddy 安装包大小（MB，用于提示）</label><input v-model.number="form.install.workbuddy_size_mb" type="number" min="1" class="input" /></div>
          </div>
          <p class="muted text-xs">这些值会写进用户电脑上运行的脚本，只接受规定格式：地址必须是 https，包名、商店 ID、winget ID 按官方格式校验，格式不对无法保存。</p>
        </section>

        <section class="card p-5 sm:p-6 space-y-4">
          <h2 class="font-semibold">WorkBuddy 模型参数 <span class="muted text-sm font-normal">· 写入 models.json</span></h2>
          <div class="grid gap-4 sm:grid-cols-2">
            <div><label class="input-label">输入 Token 上限</label><input v-model.number="form.workbuddy.max_input_tokens" type="number" min="1024" class="input" /></div>
            <div><label class="input-label">输出 Token 上限</label><input v-model.number="form.workbuddy.max_output_tokens" type="number" min="256" class="input" /></div>
          </div>
          <div class="flex flex-wrap gap-5 text-sm">
            <label class="flex items-center gap-2"><input v-model="form.workbuddy.supports_tool_call" type="checkbox" /> 工具调用</label>
            <label class="flex items-center gap-2"><input v-model="form.workbuddy.supports_images" type="checkbox" /> 图片输入</label>
            <label class="flex items-center gap-2"><input v-model="form.workbuddy.supports_reasoning" type="checkbox" /> 思考模式</label>
          </div>
        </section>
      </div>

      <!-- CC Switch 下载 -->
      <div v-if="tab === 'ccswitch'" class="space-y-4">
        <section class="card p-5 sm:p-6 space-y-4">
          <h2 class="font-semibold">Windows 安装包</h2>
          <div class="grid gap-4 sm:grid-cols-2">
            <div><label class="input-label">版本号</label><input v-model.trim="form.ccswitch.version" class="input" placeholder="3.20.4" /></div>
            <div><label class="input-label">GitHub 发布页</label><input v-model.trim="form.ccswitch.releases_url" class="input" /></div>
          </div>
          <div class="flex gap-5 text-sm">
            <label class="flex items-center gap-2"><input type="radio" :checked="form.ccswitch.windows.source === 'url'" @change="setDownloadSource('url')" /> 填写下载地址</label>
            <label class="flex items-center gap-2"><input type="radio" :checked="form.ccswitch.windows.source === 'file'" :disabled="!files.length" @change="setDownloadSource('file')" /> 使用上传的文件</label>
          </div>
          <div v-if="form.ccswitch.windows.source === 'url'">
            <label class="input-label">下载地址（https，或手册内的 assets/downloads/ 文件）</label>
            <input v-model.trim="form.ccswitch.windows.url" class="input" />
          </div>
          <div v-else>
            <label class="input-label">选择文件</label>
            <select v-model.number="form.ccswitch.windows.file_id" class="input">
              <option v-for="f in files" :key="f.id" :value="f.id">{{ f.file_name }}（{{ formatSize(f.file_size) }}）</option>
            </select>
            <p v-if="selectedFile" class="muted mt-1 break-all text-xs">SHA-256：{{ selectedFile.sha256 }}</p>
          </div>
        </section>

        <section class="card p-5 sm:p-6 space-y-4">
          <h2 class="font-semibold">文件库 <span class="muted text-sm font-normal">· 安装包、压缩包、PDF、图片，单个最大 100 MB</span></h2>
          <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <input ref="fileInput" type="file" class="input" accept=".msi,.exe,.dmg,.pkg,.zip,.7z,.pdf,.png,.jpg,.jpeg,.webp" />
            <input v-model="fileDescription" class="input" maxlength="200" placeholder="说明（可选），例如 CC Switch 3.21.0" />
            <button type="button" class="btn-primary" :disabled="uploading" @click="upload">{{ uploading ? '上传中…' : '上传' }}</button>
          </div>
          <div v-if="files.length" class="table-wrap">
            <table class="table">
              <thead><tr><th>文件</th><th>大小</th><th>上传</th><th></th></tr></thead>
              <tbody>
                <tr v-for="f in files" :key="f.id">
                  <td>
                    <a class="link break-all" :href="f.download_path" target="_blank" rel="noopener">{{ f.file_name }}</a>
                    <p v-if="f.description" class="muted text-xs">{{ f.description }}</p>
                  </td>
                  <td class="whitespace-nowrap">{{ formatSize(f.file_size) }}</td>
                  <td class="whitespace-nowrap text-xs">{{ f.uploaded_by_name || '-' }}<br />{{ formatDateTime(f.created_at) }}</td>
                  <td class="whitespace-nowrap text-right">
                    <button type="button" class="btn-ghost btn-sm" @click="useFile(f)">设为 Windows 下载</button>
                    <button type="button" class="btn-ghost btn-sm text-red-600" @click="removeFile(f)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="muted text-sm">还没有上传文件。</p>
        </section>
      </div>

      <!-- 分组说明 -->
      <ManualGroupsEditor v-if="tab === 'groups'" v-model="form.groups" :err-msg="errMsg" />

      <!-- 预览 -->
      <div v-if="tab === 'preview'" class="space-y-4">
        <section class="card p-5 sm:p-6 space-y-4">
          <p class="muted text-sm">用<strong>正在编辑、还没保存</strong>的规则试算：手册读取模型后，每个客户端会列出哪些模型、默认选哪个。</p>
          <div class="flex gap-5 text-sm">
            <label class="flex items-center gap-2"><input v-model="preview.mode" type="radio" value="list" /> 粘贴模型 ID 列表</label>
            <label class="flex items-center gap-2"><input v-model="preview.mode" type="radio" value="key" /> 用一把 Key 读取</label>
          </div>
          <textarea v-if="preview.mode === 'list'" v-model="preview.list" class="input font-mono text-sm" rows="4" placeholder="每行一个，或用空格、逗号分隔，例如&#10;claude-sonnet-5-5&#10;gpt-6.1-sol"></textarea>
          <input v-else v-model="preview.key" class="input [-webkit-text-security:disc]" autocomplete="off" spellcheck="false" placeholder="粘贴 Key（只在本页使用，不保存）" />
          <div class="flex items-center gap-3">
            <button type="button" class="btn-primary btn-sm" :disabled="preview.loading" @click="runPreview">{{ preview.loading ? '读取中…' : '试算' }}</button>
            <span v-if="preview.error" class="text-sm text-red-600">{{ preview.error }}</span>
            <span v-else-if="preview.ids.length" class="muted text-sm">共 {{ preview.ids.length }} 个模型</span>
          </div>
        </section>
        <div v-if="previewResult" class="grid gap-4 lg:grid-cols-3">
          <section v-for="client in CLIENTS" :key="client.key" class="card p-5">
            <h2 class="font-semibold">{{ client.label }}</h2>
            <p class="mt-2 text-sm">默认选中：<code class="font-semibold">{{ previewResult.clients[client.key].recommended || '（没有可用模型）' }}</code></p>
            <ul class="mt-2 space-y-0.5 text-sm">
              <li v-for="m in previewResult.clients[client.key].models" :key="m"><code>{{ m }}</code></li>
            </ul>
            <dl v-if="client.key === 'claude' && previewResult.clients.claude.models.length" class="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 border-t pt-3 text-sm">
              <template v-for="role in ROLES" :key="role.key">
                <dt class="muted">{{ role.label }}</dt><dd><code>{{ previewResult.roles[role.key] || '跟随默认' }}</code></dd>
              </template>
            </dl>
          </section>
        </div>
      </div>

      <!-- 版本历史 -->
      <div v-if="tab === 'history'" class="space-y-4">
        <div class="table-wrap card">
          <table class="table">
            <thead><tr><th>版本</th><th>时间</th><th>修改人</th><th>备注</th><th></th></tr></thead>
            <tbody>
              <tr v-for="v in versions" :key="v.version">
                <td class="whitespace-nowrap">
                  v{{ v.version }}
                  <span v-if="v.version === live.version" class="badge badge-primary ml-1">当前</span>
                </td>
                <td class="whitespace-nowrap text-sm">{{ formatDateTime(v.created_at) }}</td>
                <td class="text-sm">{{ v.created_by_name || '系统' }}</td>
                <td class="text-sm">{{ v.note || '-' }}</td>
                <td class="whitespace-nowrap text-right">
                  <template v-if="v.version !== live.version">
                    <button type="button" class="btn-ghost btn-sm" @click="showDiff(v.version)">与当前对比</button>
                    <button type="button" class="btn-ghost btn-sm" @click="restore(v.version)">恢复到此版本</button>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <section v-if="compare" class="card p-5 sm:p-6">
          <div class="flex items-center justify-between">
            <h2 class="font-semibold">版本 {{ compare.version }} → 当前版本 {{ live.version }}</h2>
            <button type="button" class="btn-ghost btn-sm" @click="compare = null">关闭</button>
          </div>
          <p v-if="!compare.rows.length" class="muted mt-3 text-sm">两个版本内容相同。</p>
          <div v-else class="table-wrap mt-3">
            <table class="table">
              <thead><tr><th>配置项</th><th>版本 {{ compare.version }}</th><th>当前</th></tr></thead>
              <tbody>
                <tr v-for="row in compare.rows" :key="row.path">
                  <td class="text-sm">{{ fieldLabel(row.path) || row.path }}</td>
                  <td class="break-all text-sm"><code>{{ row.before }}</code></td>
                  <td class="break-all text-sm"><code>{{ row.after }}</code></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <!-- 保存栏 -->
      <div class="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur">
        <div class="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
          <span class="text-sm" :class="dirty ? 'text-amber-700' : 'muted'">{{ dirty ? '有未保存的修改' : '没有修改' }}</span>
          <input v-model="note" class="input min-w-[12rem] flex-1" maxlength="200" placeholder="修改说明（可选），例如：Codex 推荐改为 gpt-6-luna" />
          <label class="flex items-center gap-2 text-sm"><input v-model="touchDate" type="checkbox" /> 更新时间改为今天</label>
          <button type="button" class="btn-secondary" :disabled="!dirty || saving" @click="discard">放弃修改</button>
          <button type="button" class="btn-primary" :disabled="!dirty || saving" @click="save">{{ saving ? '保存中…' : '保存并生效' }}</button>
        </div>
      </div>
    </template>
  </div>
</template>
