<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const items = ref<any[]>([])
const tab = ref('all')
const keyword = ref('')

async function load() {
  const params: any = { page_size: 50, keyword: keyword.value || undefined }
  if (tab.value === 'unclaimed') params.unclaimed = true
  if (tab.value === 'mine') params.claimed_by = auth.me?.id
  if (tab.value === 'PROCESSING') params.status = 'PROCESSING'
  if (tab.value === 'WAITING_USER') params.status = 'WAITING_USER'
  if (tab.value === 'RESOLVED') params.status = 'RESOLVED'
  if (tab.value === 'CLOSED') params.status = 'CLOSED'
  const { data } = await api.get('/admin/tickets', { params })
  items.value = data.items
}

onMounted(load)

const tabs = [
  { id: 'all', label: '全部' },
  { id: 'unclaimed', label: '未认领' },
  { id: 'mine', label: '我认领' },
  { id: 'PROCESSING', label: '处理中' },
  { id: 'WAITING_USER', label: '等待用户' },
  { id: 'RESOLVED', label: '已解决' },
  { id: 'CLOSED', label: '已关闭' },
]
</script>

<template>
  <div>
    <h1 class="text-xl font-semibold mb-4">工单管理</h1>
    <div class="flex flex-wrap gap-2 mb-3 text-sm">
      <button
        v-for="t in tabs"
        :key="t.id"
        class="px-3 py-1 rounded border"
        :class="tab === t.id ? 'bg-sky-600 text-white border-sky-600' : 'bg-white'"
        @click="tab = t.id; load()"
      >{{ t.label }}</button>
    </div>
    <div class="mb-3 flex gap-2">
      <input v-model="keyword" class="border rounded px-2 py-1 text-sm" placeholder="搜索单号/标题" @keyup.enter="load" />
      <button class="border px-2 py-1 rounded text-sm" @click="load">搜索</button>
    </div>
    <table class="w-full bg-white shadow rounded text-sm">
      <thead class="bg-slate-100 text-left">
        <tr>
          <th class="p-2">单号</th>
          <th class="p-2">标题</th>
          <th class="p-2">优先级</th>
          <th class="p-2">状态</th>
          <th class="p-2">认领人</th>
          <th class="p-2">创建</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in items" :key="t.id" class="border-t">
          <td class="p-2">
            <RouterLink class="text-sky-700" :to="`/admin/tickets/${t.id}`">{{ t.ticket_no }}</RouterLink>
          </td>
          <td class="p-2">{{ t.title }}</td>
          <td class="p-2">{{ t.priority }}</td>
          <td class="p-2">{{ t.status }}</td>
          <td class="p-2">{{ t.claimed_by_user_id || '-' }}</td>
          <td class="p-2">{{ t.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
