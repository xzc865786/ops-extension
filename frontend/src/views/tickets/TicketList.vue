<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'

const items = ref<any[]>([])
const status = ref('')
const loading = ref(true)

async function load() {
  loading.value = true
  const { data } = await api.get('/tickets', { params: { status: status.value || undefined } })
  items.value = data.items
  loading.value = false
}

onMounted(load)

const statusLabel: Record<string, string> = {
  OPEN: '待处理',
  PROCESSING: '处理中',
  WAITING_USER: '等待用户',
  RESOLVED: '已解决',
  CLOSED: '已关闭',
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="page-title">我的工单</h1>
      <RouterLink
        to="/tickets/new"
        class="btn-primary"
      >新建工单</RouterLink>
    </div>
    <div class="mb-3 flex gap-2 items-center text-sm">
      <label>状态</label>
      <select v-model="status" class="input" @change="load">
        <option value="">全部</option>
        <option v-for="(l, k) in statusLabel" :key="k" :value="k">{{ l }}</option>
      </select>
    </div>
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else class="table-wrap"><table class="table">
      <thead class="text-left">
        <tr>
          <th class="p-2">单号</th>
          <th class="p-2">标题</th>
          <th class="p-2">分类</th>
          <th class="p-2">优先级</th>
          <th class="p-2">状态</th>
          <th class="p-2">创建时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in items" :key="t.id" class="border-t hover:bg-dark-700/40">
          <td class="p-2">
            <RouterLink class="link" :to="`/tickets/${t.id}`">{{ t.ticket_no }}</RouterLink>
          </td>
          <td class="p-2">{{ t.title }}</td>
          <td class="p-2">{{ t.category }}</td>
          <td class="p-2">{{ t.priority }}</td>
          <td class="p-2">{{ statusLabel[t.status] || t.status }}</td>
          <td class="p-2">{{ t.created_at }}</td>
        </tr>
        <tr v-if="!items.length"><td colspan="6" class="p-4 text-center muted">暂无工单</td></tr>
      </tbody>
    </table></div>
  </div>
</template>
