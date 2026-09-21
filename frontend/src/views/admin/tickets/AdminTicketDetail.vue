<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api/client'

const route = useRoute()
const ticket = ref<any>(null)
const reply = ref('')
const isInternal = ref(false)
const patch = reactive({ status: '', category: '', priority: '' })
const meta = ref<any>({ categories: [], priorities: [], statuses: [] })

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

async function claim() { await api.post(`/admin/tickets/${route.params.id}/claim`); await load() }
async function unclaim() { await api.post(`/admin/tickets/${route.params.id}/unclaim`); await load() }
async function takeover() { await api.post(`/admin/tickets/${route.params.id}/takeover`); await load() }
async function close() { await api.post(`/admin/tickets/${route.params.id}/close`); await load() }
async function savePatch() {
  await api.patch(`/admin/tickets/${route.params.id}`, {
    status: patch.status,
    category: patch.category,
    priority: patch.priority,
  })
  await load()
}
async function send() {
  await api.post(`/admin/tickets/${route.params.id}/replies`, {
    content: reply.value,
    is_internal: isInternal.value,
  })
  reply.value = ''
  isInternal.value = false
  await load()
}
</script>

<template>
  <div v-if="ticket" class="space-y-4">
    <div class="bg-white rounded shadow p-4">
      <h1 class="text-xl font-semibold">{{ ticket.title }}</h1>
      <p class="text-sm text-slate-500">{{ ticket.ticket_no }} · 创建者 {{ ticket.creator_user_id }}</p>
      <div class="whitespace-pre-wrap text-sm mt-2">{{ ticket.description }}</div>
      <div class="flex flex-wrap gap-2 mt-3 text-sm">
        <button class="border px-2 py-1 rounded" @click="claim">认领</button>
        <button class="border px-2 py-1 rounded" @click="unclaim">释放</button>
        <button class="border px-2 py-1 rounded" @click="takeover">接管</button>
        <button class="border px-2 py-1 rounded text-red-600" @click="close">关闭</button>
      </div>
      <div class="grid grid-cols-3 gap-2 mt-3 text-sm">
        <select v-model="patch.status" class="border rounded px-2 py-1">
          <option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
        <select v-model="patch.category" class="border rounded px-2 py-1">
          <option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option>
        </select>
        <select v-model="patch.priority" class="border rounded px-2 py-1">
          <option v-for="p in meta.priorities" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>
      <button class="mt-2 bg-sky-600 text-white px-3 py-1 rounded text-sm" @click="savePatch">保存变更</button>
    </div>

    <div class="bg-white rounded shadow p-4">
      <h2 class="font-medium mb-2">消息 / 内部备注</h2>
      <div v-for="m in ticket.messages" :key="m.id" class="border-b py-2 text-sm" :class="m.is_internal ? 'bg-amber-50' : ''">
        <div class="text-xs text-slate-400">
          {{ m.sender_role }} · {{ m.created_at }}
          <span v-if="m.is_internal" class="text-amber-700">（内部）</span>
        </div>
        <div class="whitespace-pre-wrap">{{ m.content }}</div>
      </div>
      <textarea v-model="reply" rows="3" class="border rounded w-full px-2 py-1.5 text-sm mt-2" />
      <label class="flex items-center gap-2 text-sm mt-1">
        <input v-model="isInternal" type="checkbox" /> 内部备注（用户不可见）
      </label>
      <button class="mt-2 bg-sky-600 text-white px-3 py-1.5 rounded text-sm" @click="send">发送</button>
    </div>

    <div class="bg-white rounded shadow p-4">
      <h2 class="font-medium mb-2">事件时间线</h2>
      <ul class="text-sm space-y-1">
        <li v-for="e in ticket.events" :key="e.id">
          <span class="text-slate-400">{{ e.created_at }}</span> · {{ e.event_type }}
        </li>
      </ul>
    </div>
  </div>
</template>
