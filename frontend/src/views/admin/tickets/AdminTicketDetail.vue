<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'
import StatusBadge from '@/components/StatusBadge.vue'
import FormDataView from '@/components/tickets/FormDataView.vue'
import { downloadAttachment } from '@/utils/attachments'
import { formatDateTime, labelFor } from '@/utils/display'

const route = useRoute()
const toast = useToast()
const ticket = ref<any>(null)
const reply = ref('')
const isInternal = ref(false)
const patch = reactive({ status: '', category: '', priority: '' })
const meta = ref<any>({ categories: [], priorities: [], statuses: [] })
const error = ref('')
const successBanner = ref('')
const showCloseConfirm = ref(false)
const closing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFileName = ref('')
const busy = ref(false)

const isClosed = computed(() => ticket.value?.status === 'CLOSED')
const attachments = computed(() => ticket.value?.attachments ?? [])

async function load() {
  const [{ data: t }, { data: m }] = await Promise.all([
    api.get(`/admin/tickets/${route.params.id}`),
    api.get('/tickets/meta'),
  ])
  ticket.value = t
  meta.value = m
  patch.status = t.status
  patch.category = t.category
  patch.priority = t.priority
}

onMounted(load)

function errMsg(e: any, fallback: string) {
  return e.response?.data?.detail?.detail || e.response?.data?.detail || fallback
}

async function claim() {
  try {
    await api.post(`/admin/tickets/${route.params.id}/claim`)
    await load()
    toast.success('已认领')
  } catch (e: any) {
    error.value = errMsg(e, '认领失败')
    toast.error(error.value)
  }
}
async function unclaim() {
  try {
    await api.post(`/admin/tickets/${route.params.id}/unclaim`)
    await load()
    toast.success('已释放')
  } catch (e: any) {
    error.value = errMsg(e, '释放失败')
    toast.error(error.value)
  }
}
async function takeover() {
  try {
    await api.post(`/admin/tickets/${route.params.id}/takeover`)
    await load()
    toast.success('已接管')
  } catch (e: any) {
    error.value = errMsg(e, '接管失败')
    toast.error(error.value)
  }
}

function askClose() {
  showCloseConfirm.value = true
  error.value = ''
  successBanner.value = ''
}
function cancelClose() {
  showCloseConfirm.value = false
}
async function confirmClose() {
  closing.value = true
  error.value = ''
  successBanner.value = ''
  try {
    await api.post(`/admin/tickets/${route.params.id}/close`)
    showCloseConfirm.value = false
    await load()
    successBanner.value = '工单已关闭'
    toast.success('工单已关闭')
  } catch (e: any) {
    error.value = errMsg(e, '关闭失败')
    toast.error(error.value)
  } finally {
    closing.value = false
  }
}

async function savePatch() {
  error.value = ''
  try {
    await api.patch(`/admin/tickets/${route.params.id}`, {
      status: patch.status,
      category: patch.category,
      priority: patch.priority,
    })
    await load()
    toast.success('变更已保存')
  } catch (e: any) {
    error.value = errMsg(e, '保存失败')
    toast.error(error.value)
  }
}

async function send() {
  error.value = ''
  try {
    await api.post(`/admin/tickets/${route.params.id}/replies`, {
      content: reply.value,
      is_internal: isInternal.value,
    })
    reply.value = ''
    isInternal.value = false
    await load()
    toast.success('已发送')
  } catch (e: any) {
    error.value = errMsg(e, '发送失败')
    toast.error(error.value)
  }
}

function onFileChange() {
  const f = fileInput.value?.files?.[0]
  selectedFileName.value = f ? f.name : ''
}

async function upload() {
  const f = fileInput.value?.files?.[0]
  if (!f) {
    error.value = '请先选择文件'
    return
  }
  error.value = ''
  busy.value = true
  const fd = new FormData()
  fd.append('file', f)
  try {
    await api.post(`/admin/tickets/${route.params.id}/attachments`, fd)
    if (fileInput.value) fileInput.value.value = ''
    selectedFileName.value = ''
    await load()
    toast.success('附件上传成功')
  } catch (e: any) {
    error.value = errMsg(e, '上传失败（≤20MB，图片/PDF/日志）')
    toast.error(error.value)
  } finally {
    busy.value = false
  }
}

async function download(id: number, filename: string) {
  error.value = ''
  try {
    await downloadAttachment(id, filename)
  } catch (e: any) {
    error.value = e.message || '附件下载失败'
    toast.error(error.value)
  }
}
</script>

<template>
  <div v-if="ticket" class="space-y-4">
    <RouterLink to="/admin/tickets" class="link inline-block text-sm">← 返回工单管理</RouterLink>
    <div
      v-if="successBanner"
      class="alert-success"
    >
      {{ successBanner }}
    </div>
    <div
      v-if="error"
      class="alert-error"
    >
      {{ error }}
    </div>

    <div class="card p-5 sm:p-6">
      <h1 class="page-title">{{ ticket.title }}</h1>
      <p class="text-sm muted">
        {{ ticket.ticket_no }} · {{ labelFor(meta.categories, ticket.category) }} · 创建者 {{ ticket.creator_user_id }}
        <StatusBadge :status="ticket.status" kind="ticket" />
      </p>
      <p v-if="ticket.form_schema && ticket.form_schema.key !== ticket.category" class="text-xs muted mt-1">
        提交时的分类：{{ ticket.form_schema.label }}（以下字段按提交时的表单显示）
      </p>
      <div class="mt-3 border-t pt-3 space-y-3">
        <FormDataView :schema="ticket.form_schema" :data="ticket.form_data" />
        <div v-if="ticket.description" class="whitespace-pre-wrap text-sm">{{ ticket.description }}</div>
      </div>

      <div
        v-if="showCloseConfirm"
        class="alert-warning mt-4 space-y-2"
      >
        <p>确认关闭工单？关闭后不可重开。</p>
        <div class="flex gap-2">
          <button type="button" class="btn-danger btn-sm" :disabled="closing" @click="confirmClose">
            {{ closing ? '关闭中…' : '确认关闭' }}
          </button>
          <button type="button" class="btn-secondary btn-sm" :disabled="closing" @click="cancelClose">取消</button>
        </div>
      </div>

      <div v-if="!isClosed" class="flex flex-wrap gap-2 mt-3 text-sm">
        <button type="button" class="btn-secondary btn-sm" @click="claim">认领</button>
        <button type="button" class="btn-secondary btn-sm" @click="unclaim">释放</button>
        <button type="button" class="btn-secondary btn-sm" @click="takeover">接管</button>
        <button
          v-if="!showCloseConfirm"
          type="button"
          class="btn-danger btn-sm"
          @click="askClose"
        >关闭</button>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3 text-sm">
        <select v-model="patch.status" class="input" :disabled="isClosed">
          <option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
        <select v-model="patch.category" class="input" :disabled="isClosed">
          <option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}{{ c.enabled === false ? '（已停用）' : '' }}</option>
        </select>
        <select v-model="patch.priority" class="input" :disabled="isClosed">
          <option v-for="p in meta.priorities" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>
      <button
        v-if="!isClosed"
        type="button"
        class="mt-2 btn-primary"
        @click="savePatch"
      >保存变更</button>
    </div>

    <div class="card p-5 sm:p-6">
      <h2 class="section-title mb-2">消息 / 内部备注</h2>
      <div
        v-for="m in ticket.messages"
        :key="m.id"
        class="border-b py-2 text-sm"
        :class="m.is_internal ? 'bg-amber-500/10' : ''"
      >
        <div class="text-xs muted">
          {{ m.sender_role }} · {{ formatDateTime(m.created_at) }}
          <span v-if="m.is_internal" class="text-amber-700 dark:text-amber-400">（内部）</span>
        </div>
        <div class="whitespace-pre-wrap">{{ m.content }}</div>
      </div>
      <template v-if="!isClosed">
        <textarea v-model="reply" rows="3" class="input mt-2" />
        <label class="flex items-center gap-2 text-sm mt-1">
          <input v-model="isInternal" type="checkbox" /> 内部备注（用户不可见）
        </label>
        <button type="button" class="mt-2 btn-primary" @click="send">发送</button>
      </template>
      <p v-else class="text-sm muted mt-3">工单已关闭，无法继续回复。</p>
    </div>

    <div class="card p-5 sm:p-6">
      <h2 class="section-title mb-1">附件</h2>
      <p class="text-xs muted mb-3">限制：≤20MB；仅图片 / PDF / 日志</p>
      <ul v-if="attachments.length" class="text-sm space-y-1 mb-3">
        <li v-for="a in attachments" :key="a.id">
          <button type="button" class="link" @click="download(a.id, a.file_name)">{{ a.file_name }}</button>
          （{{ a.file_size }} bytes）
        </li>
      </ul>
      <p v-else class="text-sm muted mb-3">暂无附件。可在下方选择文件后上传。</p>
      <div v-if="!isClosed" class="flex flex-wrap gap-2 items-center">
        <label class="file-picker">
          <span class="file-picker-btn">选择文件</span>
          <span class="file-picker-name">{{ selectedFileName || '未选择文件' }}</span>
          <input
            ref="fileInput"
            type="file"
            class="sr-only"
            accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,.log,.txt"
            @change="onFileChange"
          />
        </label>
        <button
          type="button"
          class="btn-secondary btn-sm"
          :disabled="busy || !selectedFileName"
          @click="upload"
        >{{ busy ? '上传中…' : '上传' }}</button>
      </div>
    </div>

    <div class="card p-4">
      <h2 class="font-medium mb-2">事件时间线</h2>
      <ul class="text-sm space-y-1">
        <li v-for="e in ticket.events" :key="e.id">
          <span class="muted">{{ formatDateTime(e.created_at) }}</span> · {{ e.event_type }}
        </li>
      </ul>
      <p v-if="!ticket.events?.length" class="text-sm muted">暂无事件</p>
    </div>
  </div>
</template>
