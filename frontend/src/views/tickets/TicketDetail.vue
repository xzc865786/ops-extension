<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'
import StatusBadge from '@/components/StatusBadge.vue'

const route = useRoute()
const toast = useToast()
const ticket = ref<any>(null)
const reply = ref('')
const error = ref('')
const successBanner = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFileName = ref('')
const closing = ref(false)
const showCloseConfirm = ref(false)
const busy = ref(false)

const isClosed = computed(() => ticket.value?.status === 'CLOSED')
const attachments = computed(() => ticket.value?.attachments ?? [])

async function load() {
  const { data } = await api.get(`/tickets/${route.params.id}`)
  ticket.value = data
}

onMounted(load)

function onFileChange() {
  const f = fileInput.value?.files?.[0]
  selectedFileName.value = f ? f.name : ''
}

async function sendReply() {
  error.value = ''
  successBanner.value = ''
  try {
    await api.post(`/tickets/${route.params.id}/replies`, { content: reply.value })
    reply.value = ''
    await load()
    toast.success('回复已发送')
  } catch (e: any) {
    error.value = e.response?.data?.detail?.detail || e.response?.data?.detail || '回复失败'
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
    await api.post(`/tickets/${route.params.id}/close`)
    showCloseConfirm.value = false
    await load()
    successBanner.value = '工单已关闭'
    toast.success('工单已关闭')
  } catch (e: any) {
    error.value = e.response?.data?.detail?.detail || e.response?.data?.detail || '关闭失败'
    toast.error(error.value)
  } finally {
    closing.value = false
  }
}

async function upload() {
  const f = fileInput.value?.files?.[0]
  if (!f) {
    error.value = '请先选择文件'
    return
  }
  error.value = ''
  successBanner.value = ''
  busy.value = true
  const fd = new FormData()
  fd.append('file', f)
  try {
    await api.post(`/tickets/${route.params.id}/attachments`, fd)
    if (fileInput.value) fileInput.value.value = ''
    selectedFileName.value = ''
    await load()
    toast.success('附件上传成功')
    successBanner.value = '附件上传成功'
  } catch (e: any) {
    error.value = e.response?.data?.detail?.detail || e.response?.data?.detail || '上传失败（≤20MB，图片/PDF/日志）'
    toast.error(error.value)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="ticket" class="space-y-4">
    <RouterLink to="/tickets" class="link inline-block text-sm">← 返回我的工单</RouterLink>
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
      <div class="flex flex-wrap justify-between items-start gap-3">
        <div>
          <h1 class="page-title">{{ ticket.title }}</h1>
          <p class="text-sm muted mt-1">
            {{ ticket.ticket_no }} · {{ ticket.category }} · {{ ticket.priority }}
            <StatusBadge :status="ticket.status" kind="ticket" />
          </p>
        </div>
        <div v-if="!isClosed" class="shrink-0">
          <button
            v-if="!showCloseConfirm"
            type="button"
            class="btn-danger btn-sm"
            @click="askClose"
          >关闭工单</button>
        </div>
      </div>

      <div
        v-if="showCloseConfirm"
        class="alert-warning mt-4 space-y-2"
      >
        <p>确认关闭工单？关闭后不可重开。</p>
        <div class="flex gap-2">
          <button
            type="button"
            class="btn-danger btn-sm"
            :disabled="closing"
            @click="confirmClose"
          >{{ closing ? '关闭中…' : '确认关闭' }}</button>
          <button
            type="button"
            class="btn-secondary btn-sm"
            :disabled="closing"
            @click="cancelClose"
          >取消</button>
        </div>
      </div>

      <div class="mt-3 text-sm whitespace-pre-wrap border-t pt-3">{{ ticket.description }}</div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-1 text-sm mt-3">
        <p v-if="ticket.request_id">Request ID：{{ ticket.request_id }}</p>
        <p v-if="ticket.model_name">模型：{{ ticket.model_name }}</p>
        <p v-if="ticket.api_endpoint">API 接口：{{ ticket.api_endpoint }}</p>
        <p v-if="ticket.occurred_at">发生时间：{{ ticket.occurred_at }}</p>
        <p v-if="ticket.error_message" class="whitespace-pre-wrap md:col-span-2">错误信息：{{ ticket.error_message }}</p>
      </div>
      <p class="text-xs muted mt-2">标题与描述创建后不可修改，请通过回复补充信息。</p>
      <div v-if="ticket.ref_ticket_no" class="text-sm mt-2">引用原单：{{ ticket.ref_ticket_no }}</div>
    </div>

    <div class="card p-5 sm:p-6">
      <h2 class="section-title mb-2">消息</h2>
      <div v-for="m in ticket.messages" :key="m.id" class="border-b py-2 text-sm">
        <div class="text-xs muted">{{ m.sender_role }} · {{ m.created_at }}</div>
        <div class="whitespace-pre-wrap">{{ m.content }}</div>
      </div>
      <p v-if="!ticket.messages?.length" class="text-sm muted">暂无消息</p>
      <div v-if="!isClosed" class="mt-3 space-y-2">
        <textarea v-model="reply" rows="3" class="input" placeholder="回复内容" />
        <button type="button" class="btn-primary" @click="sendReply">发送回复</button>
      </div>
      <p v-else class="text-sm muted mt-3">工单已关闭，无法继续回复。</p>
    </div>

    <div class="card p-5 sm:p-6">
      <h2 class="section-title mb-1">附件</h2>
      <p class="text-xs muted mb-3">限制：≤20MB；仅图片 / PDF / 日志</p>

      <ul v-if="attachments.length" class="text-sm space-y-1 mb-3">
        <li v-for="a in attachments" :key="a.id">
          <a class="link" :href="`/ext/api/v1/attachments/${a.id}/download`" target="_blank">{{ a.file_name }}</a>
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
            accept="image/*,.pdf,.log,.txt,.json"
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
  </div>
</template>
