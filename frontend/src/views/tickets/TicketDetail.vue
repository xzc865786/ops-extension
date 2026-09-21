<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api/client'

const route = useRoute()
const ticket = ref<any>(null)
const reply = ref('')
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

async function load() {
  const { data } = await api.get(`/tickets/${route.params.id}`)
  ticket.value = data
}

onMounted(load)

async function sendReply() {
  error.value = ''
  try {
    await api.post(`/tickets/${route.params.id}/replies`, { content: reply.value })
    reply.value = ''
    await load()
  } catch (e: any) {
    error.value = e.response?.data?.detail?.detail || e.response?.data?.detail || '回复失败'
  }
}

async function closeTicket() {
  if (!confirm('确认关闭工单？关闭后不可重开。')) return
  await api.post(`/tickets/${route.params.id}/close`)
  await load()
}

async function upload() {
  const f = fileInput.value?.files?.[0]
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  try {
    await api.post(`/tickets/${route.params.id}/attachments`, fd)
    await load()
  } catch (e: any) {
    error.value = e.response?.data?.detail?.detail || '上传失败（≤20MB，图片/PDF/日志）'
  }
}
</script>

<template>
  <div v-if="ticket" class="space-y-4">
    <div class="card p-4">
      <div class="flex justify-between items-start">
        <div>
          <h1 class="page-title">{{ ticket.title }}</h1>
          <p class="text-sm muted mt-1">
            {{ ticket.ticket_no }} · {{ ticket.category }} · {{ ticket.priority }} · {{ ticket.status }}
          </p>
        </div>
        <button
          v-if="ticket.status !== 'CLOSED'"
          class="btn-secondary btn-sm"
          @click="closeTicket"
        >关闭工单</button>
      </div>
      <div class="mt-3 text-sm whitespace-pre-wrap border-t pt-3">{{ ticket.description }}</div>
      <p class="text-xs muted mt-2">标题与描述创建后不可修改，请通过回复补充信息。</p>
      <div v-if="ticket.ref_ticket_no" class="text-sm mt-2">引用原单：{{ ticket.ref_ticket_no }}</div>
    </div>

    <div class="card p-4">
      <h2 class="font-medium mb-2">消息</h2>
      <div v-for="m in ticket.messages" :key="m.id" class="border-b py-2 text-sm">
        <div class="text-xs muted">{{ m.sender_role }} · {{ m.created_at }}</div>
        <div class="whitespace-pre-wrap">{{ m.content }}</div>
      </div>
      <div v-if="ticket.status !== 'CLOSED'" class="mt-3 space-y-2">
        <textarea v-model="reply" rows="3" class="input" placeholder="回复内容" />
        <button class="btn-primary px-3 py-1.5 rounded text-sm" @click="sendReply">发送回复</button>
      </div>
      <p v-if="error" class="text-red-400 text-sm mt-2">{{ error }}</p>
    </div>

    <div class="card p-4">
      <h2 class="font-medium mb-2">附件</h2>
      <ul class="text-sm space-y-1">
        <li v-for="a in ticket.attachments" :key="a.id">
          <a class="link" :href="`/ext/api/v1/attachments/${a.id}/download`" target="_blank">{{ a.file_name }}</a>
          （{{ a.file_size }} bytes）
        </li>
      </ul>
      <div v-if="ticket.status !== 'CLOSED'" class="mt-2 flex gap-2 items-center">
        <input ref="fileInput" type="file" class="text-sm" />
        <button class="btn-secondary btn-sm" @click="upload">上传</button>
      </div>
    </div>
  </div>
</template>
