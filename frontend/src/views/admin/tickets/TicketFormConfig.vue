<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'
import DynamicForm from '@/components/tickets/DynamicForm.vue'
import FieldEditor from '@/components/tickets/FieldEditor.vue'
import { formatDateTime } from '@/utils/display'
import {
  BUILTIN_CATEGORIES, CATEGORY_KEY_RE, FIELD_KEY_RE, KIND_LABELS, initialValues,
  type FormCategory, type FormField,
} from '@/utils/ticketForm'

const toast = useToast()
const tab = ref<'editor' | 'history'>('editor')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const live = ref<any>(null)
const defaults = ref<any>(null)
const form = ref<{ schema: number; categories: FormCategory[] } | null>(null)
const versions = ref<any[]>([])
const note = ref('')
const selectedKey = ref('')

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const dirty = computed(() => !!form.value && JSON.stringify(form.value) !== JSON.stringify(live.value?.config))
const selected = computed(() => form.value?.categories.find((c) => c.key === selectedKey.value) || null)

// Stable ids so editors keep their open state while keys are edited or rows move.
const ids = new WeakMap<object, number>()
let nextId = 1
const idOf = (item: object) => ids.get(item) ?? (ids.set(item, nextId++), ids.get(item)!)

function errMsg(e: any, fallback: string) {
  const d = e.response?.data
  return d?.detail?.detail || (typeof d?.detail === 'string' ? d.detail : '') || fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [config, versionList] = await Promise.all([
      api.get('/admin/tickets/form-config'),
      api.get('/admin/tickets/form-config/versions'),
    ])
    live.value = config.data
    defaults.value = config.data.defaults
    form.value = clone(config.data.config)
    versions.value = versionList.data
    if (!selected.value) selectedKey.value = form.value!.categories[0]?.key || ''
  } catch (e: any) {
    error.value = errMsg(e, '加载表单配置失败')
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
    await api.put('/admin/tickets/form-config', {
      config: form.value,
      base_version: live.value.version,
      note: note.value.trim() || null,
    })
    note.value = ''
    await load()
    toast.success(`已保存为版本 ${live.value.version}，用户刷新页面后生效`)
  } catch (e: any) {
    error.value = errMsg(e, '保存失败')
    toast.error('保存失败，请查看页面顶部的错误说明')
  } finally {
    saving.value = false
  }
}

function discard() {
  form.value = clone(live.value.config)
  error.value = ''
  if (!selected.value) selectedKey.value = form.value!.categories[0]?.key || ''
}

function loadDefaults() {
  if (!confirm('把表单配置改回初始默认值？自定义分类会被移除（已有工单的分类无法移除，保存时会提示）。需要点“保存”才会生效。')) return
  form.value = clone(defaults.value)
  if (!selected.value) selectedKey.value = form.value!.categories[0]?.key || ''
  toast.push('已载入默认值，确认无误后点“保存”')
}

// ---- categories ------------------------------------------------------------
const newCategory = reactive({ open: false, key: '', label: '' })

function moveCategory(index: number, delta: number) {
  const list = form.value!.categories
  const [item] = list.splice(index, 1)
  list.splice(index + delta, 0, item)
}

function addCategory() {
  const key = newCategory.key.trim().toUpperCase()
  const label = newCategory.label.trim()
  if (!CATEGORY_KEY_RE.test(key)) {
    toast.error('分类标识须以大写字母开头，只能包含大写字母、数字和下划线（2 到 40 位）')
    return
  }
  if (form.value!.categories.some((c) => c.key === key)) {
    toast.error('分类标识已存在')
    return
  }
  if (!label) {
    toast.error('请填写分类名称')
    return
  }
  form.value!.categories.push({
    key, label, description: '', kind: 'general', enabled: true, notice: '', title_mode: 'required',
    title_template: '', description_mode: 'required', require_attachment: false, attachment_hint: '', fields: [],
  })
  selectedKey.value = key
  Object.assign(newCategory, { open: false, key: '', label: '' })
}

function removeCategory(c: FormCategory) {
  if (!confirm(`删除分类“${c.label}”？已有工单的分类无法删除，只能停用。`)) return
  form.value!.categories = form.value!.categories.filter((x) => x !== c)
  selectedKey.value = form.value!.categories[0]?.key || ''
}

// ---- fields ----------------------------------------------------------------
const newFieldId = ref<number | null>(null)

function addField() {
  const c = selected.value!
  let n = c.fields.length + 1
  while (c.fields.some((f) => f.key === `field_${n}`)) n += 1
  const field: FormField = { key: `field_${n}`, label: '新字段', type: 'text', required: false, help: '', placeholder: '', options: [] }
  c.fields.push(field)
  newFieldId.value = idOf(c.fields[c.fields.length - 1]) // the reactive proxy, as the template sees it
}

function moveField(index: number, delta: number) {
  const fields = selected.value!.fields
  const [item] = fields.splice(index, 1)
  fields.splice(index + delta, 0, item)
}

function removeField(index: number) {
  const fields = selected.value!.fields
  const key = fields[index].key
  const dependants = fields.filter((f) => f.show_if?.field === key)
  if (dependants.length && !confirm(`“${dependants.map((f) => f.label).join('、')}”的显示条件依赖这个字段，删除后会改为总是显示。继续？`)) return
  dependants.forEach((f) => { f.show_if = null })
  fields.splice(index, 1)
}

const badKeys = computed(() => (selected.value?.fields || []).filter((f) => !FIELD_KEY_RE.test(f.key)).map((f) => f.key))

// ---- preview ---------------------------------------------------------------
const previewValues = reactive<Record<string, any>>({})
const previewFields = computed(() => selected.value?.fields || [])
watch(() => selected.value?.key, () => {
  for (const key of Object.keys(previewValues)) delete previewValues[key]
  Object.assign(previewValues, initialValues(previewFields.value))
}, { immediate: true })
watch(previewFields, (fields) => {
  for (const f of fields) if (!(f.key in previewValues)) previewValues[f.key] = initialValues([f])[f.key]
}, { deep: true })

// ---- history ---------------------------------------------------------------
async function restore(version: number) {
  if (dirty.value && !confirm('当前有未保存的修改，恢复后这些修改会丢失。继续？')) return
  if (!confirm(`恢复到版本 ${version}？会生成一个新版本，旧版本都保留。`)) return
  try {
    await api.post(`/admin/tickets/form-config/versions/${version}/restore`, { base_version: live.value.version })
    await load()
    toast.success(`已恢复到版本 ${version}（新版本 ${live.value.version}）`)
  } catch (e: any) {
    toast.error(errMsg(e, '恢复失败'))
  }
}
</script>

<template>
  <div class="pb-28">
    <RouterLink to="/admin/tickets" class="link mb-2 inline-block text-sm">← 返回工单管理</RouterLink>
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">工单表单配置</h1>
        <p v-if="live" class="page-subtitle">
          当前版本 {{ live.version }} · {{ live.created_by_name || '系统' }} · {{ formatDateTime(live.created_at) }}
        </p>
      </div>
      <div class="page-toolbar-actions">
        <button type="button" class="btn-ghost btn-sm" :disabled="!form" @click="loadDefaults">恢复默认值</button>
      </div>
    </div>

    <div v-if="error" class="alert-error mb-4 whitespace-pre-wrap" role="alert">{{ error }}</div>
    <div v-if="loading && !form" class="card p-6 muted">加载中…</div>

    <template v-if="form">
      <div class="tabs mb-4 w-fit max-w-full">
        <button type="button" class="tab" :class="tab === 'editor' ? 'tab-active' : ''" @click="tab = 'editor'">分类与字段</button>
        <button type="button" class="tab" :class="tab === 'history' ? 'tab-active' : ''" @click="tab = 'history'">版本历史</button>
      </div>

      <div v-if="tab === 'editor'" class="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_340px]">
        <!-- 分类列表 -->
        <aside class="card h-fit p-3">
          <ul class="space-y-1">
            <li v-for="(c, i) in form.categories" :key="idOf(c)" class="flex items-center gap-1">
              <button
                type="button"
                class="min-w-0 flex-1 rounded-lg px-2 py-1.5 text-left text-sm"
                :class="c.key === selectedKey ? 'bg-primary-50 font-medium text-primary-700 dark:bg-primary-900/20 dark:text-primary-300' : 'hover:bg-gray-50 dark:hover:bg-dark-700'"
                @click="selectedKey = c.key"
              >
                <span :class="c.enabled ? '' : 'line-through opacity-60'">{{ c.label }}</span>
                <span v-if="!c.enabled" class="muted ml-1 text-xs">停用</span>
              </button>
              <button type="button" class="btn-ghost btn-sm px-1.5" :disabled="i === 0" aria-label="上移" @click="moveCategory(i, -1)">↑</button>
              <button type="button" class="btn-ghost btn-sm px-1.5" :disabled="i === form.categories.length - 1" aria-label="下移" @click="moveCategory(i, 1)">↓</button>
            </li>
          </ul>
          <div class="mt-3 border-t pt-3">
            <button v-if="!newCategory.open" type="button" class="btn-secondary btn-sm w-full" @click="newCategory.open = true">新增分类</button>
            <div v-else class="space-y-2">
              <input v-model="newCategory.label" class="input" maxlength="30" placeholder="名称，例如 合作咨询" />
              <input v-model="newCategory.key" class="input font-mono" maxlength="40" placeholder="标识，例如 PARTNERSHIP" />
              <div class="flex gap-2">
                <button type="button" class="btn-primary btn-sm" @click="addCategory">添加</button>
                <button type="button" class="btn-ghost btn-sm" @click="newCategory.open = false">取消</button>
              </div>
              <p class="muted text-xs">标识保存在工单里，创建后不能修改。</p>
            </div>
          </div>
        </aside>

        <!-- 分类设置与字段 -->
        <div v-if="selected" class="min-w-0 space-y-4">
          <section class="card space-y-4 p-5">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="section-title">{{ selected.label }}</h2>
              <span class="badge-gray font-mono">{{ selected.key }}</span>
              <span class="badge-primary">业务类型：{{ KIND_LABELS[selected.kind] }}</span>
              <label class="ml-auto flex items-center gap-2 text-sm"><input v-model="selected.enabled" type="checkbox" /> 启用</label>
              <button
                v-if="!BUILTIN_CATEGORIES.includes(selected.key)"
                type="button"
                class="btn-ghost btn-sm text-red-600"
                @click="removeCategory(selected)"
              >删除分类</button>
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <div>
                <label class="input-label">名称</label>
                <input v-model="selected.label" class="input" maxlength="30" />
              </div>
              <div>
                <label class="input-label">一句话说明（显示在分类卡片上）</label>
                <input v-model="selected.description" class="input" maxlength="100" />
              </div>
            </div>
            <div>
              <label class="input-label">分类提示（显示在表单顶部，纯文本，最多 500 字）</label>
              <textarea v-model="selected.notice" class="input" rows="2" maxlength="500" />
            </div>
            <div class="grid gap-3 sm:grid-cols-3">
              <div>
                <label class="input-label">标题</label>
                <select v-model="selected.title_mode" class="input">
                  <option value="required">用户必填</option>
                  <option value="optional">选填，留空自动生成</option>
                  <option value="auto">自动生成，不显示输入框</option>
                </select>
              </div>
              <div class="sm:col-span-2">
                <label class="input-label">标题模板</label>
                <input v-model="selected.title_template" class="input" maxlength="100" placeholder="例如 退款申请 · {order_no}" />
                <p class="muted mt-1 text-xs">用 {字段标识} 引用字段的值，{category} 表示分类名称。</p>
              </div>
            </div>
            <div class="grid gap-3 sm:grid-cols-3">
              <div>
                <label class="input-label">问题描述框</label>
                <select v-model="selected.description_mode" class="input">
                  <option value="required">必填</option>
                  <option value="optional">选填</option>
                  <option value="hidden">不显示</option>
                </select>
              </div>
              <div class="sm:col-span-2">
                <label class="input-label">附件提示</label>
                <input v-model="selected.attachment_hint" class="input" maxlength="200" placeholder="例如 请上传付款截图（含交易号）" />
                <label class="mt-2 flex items-center gap-2 text-sm"><input v-model="selected.require_attachment" type="checkbox" /> 必须上传附件</label>
              </div>
            </div>
          </section>

          <section class="card space-y-3 p-5">
            <div class="flex items-center justify-between">
              <h2 class="section-title">字段 <span class="muted text-sm font-normal">· {{ selected.fields.length }} 个</span></h2>
              <button type="button" class="btn-secondary btn-sm" :disabled="selected.fields.length >= 30" @click="addField">添加字段</button>
            </div>
            <p v-if="selected.kind !== 'general'" class="muted text-xs">
              标“系统字段”的字段供订单校验、退款或开票流程使用，可以修改名称和提示，不能删除或修改类型。
            </p>
            <p v-if="badKeys.length" class="text-xs text-red-600">
              字段标识须以小写字母开头，只能包含小写字母、数字和下划线：{{ badKeys.join('、') }}
            </p>
            <FieldEditor
              v-for="(f, i) in selected.fields"
              :key="idOf(f)"
              :field="f"
              :earlier="selected.fields.slice(0, i)"
              :first="i === 0"
              :last="i === selected.fields.length - 1"
              :start-open="idOf(f) === newFieldId"
              @up="moveField(i, -1)"
              @down="moveField(i, 1)"
              @remove="removeField(i)"
            />
            <p v-if="!selected.fields.length" class="muted text-sm">没有额外字段，用户只填写标题和问题描述。</p>
          </section>
        </div>

        <!-- 预览 -->
        <aside v-if="selected" class="card h-fit space-y-4 p-5 lg:col-span-2 xl:col-span-1 xl:sticky xl:top-4">
          <h2 class="section-title">用户看到的表单</h2>
          <p v-if="selected.notice" class="whitespace-pre-wrap rounded-xl border border-primary-200 bg-primary-50 px-3 py-2 text-xs text-primary-800 dark:border-primary-900/50 dark:bg-primary-900/20 dark:text-primary-300">{{ selected.notice }}</p>
          <div v-if="selected.title_mode !== 'auto'">
            <label class="input-label">标题<span v-if="selected.title_mode === 'required'" class="text-red-500"> *</span></label>
            <input class="input" disabled />
          </div>
          <DynamicForm :fields="previewFields" :values="previewValues" id-prefix="preview" />
          <div v-if="selected.description_mode !== 'hidden'">
            <label class="input-label">{{ selected.fields.length ? '补充说明' : '问题描述' }}<span v-if="selected.description_mode === 'required'" class="text-red-500"> *</span></label>
            <textarea class="input" rows="2" disabled />
          </div>
          <p class="muted text-xs">预览可以填写，用来检查显示条件；不会提交。</p>
        </aside>
      </div>

      <div v-if="tab === 'history'" class="table-wrap card">
        <table class="table">
          <thead><tr><th>版本</th><th>时间</th><th>修改人</th><th>备注</th><th></th></tr></thead>
          <tbody>
            <tr v-for="v in versions" :key="v.version">
              <td class="whitespace-nowrap">
                v{{ v.version }}
                <span v-if="v.version === live.version" class="badge-primary ml-1">当前</span>
              </td>
              <td class="whitespace-nowrap text-sm">{{ formatDateTime(v.created_at) }}</td>
              <td class="text-sm">{{ v.created_by_name || '系统' }}</td>
              <td class="text-sm">{{ v.note || '-' }}</td>
              <td class="whitespace-nowrap text-right">
                <button v-if="v.version !== live.version" type="button" class="btn-ghost btn-sm" @click="restore(v.version)">恢复到此版本</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 保存栏 -->
      <div class="fixed inset-x-0 bottom-0 z-20 border-t border-gray-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-dark-700 dark:bg-dark-900/95">
        <div class="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
          <span class="text-sm" :class="dirty ? 'text-amber-700' : 'muted'">{{ dirty ? '有未保存的修改' : '没有修改' }}</span>
          <input v-model="note" class="input min-w-[12rem] flex-1" maxlength="200" placeholder="修改说明（可选），例如：退款增加“到账账户”字段" />
          <button type="button" class="btn-secondary" :disabled="!dirty || saving" @click="discard">放弃修改</button>
          <button type="button" class="btn-primary" :disabled="!dirty || saving" @click="save">{{ saving ? '保存中…' : '保存并生效' }}</button>
        </div>
      </div>
    </template>
  </div>
</template>
