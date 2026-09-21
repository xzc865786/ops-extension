<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'

const items = ref<any[]>([])
const status = ref('')

async function load() {
  const { data } = await api.get('/admin/expenses', {
    params: { status: status.value || undefined, page_size: 50 },
  })
  items.value = data.items
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex justify-between mb-4">
      <h1 class="text-xl font-semibold">报账管理</h1>
      <RouterLink to="/admin/expenses/new" class="bg-sky-600 text-white px-3 py-1.5 rounded text-sm">新建报账</RouterLink>
    </div>
    <select v-model="status" class="border rounded px-2 py-1 text-sm mb-3" @change="load">
      <option value="">全部状态</option>
      <option>DRAFT</option><option>SUBMITTED</option><option>APPROVED</option>
      <option>REJECTED</option><option>PAID</option><option>CANCELLED</option>
    </select>
    <table class="w-full bg-white shadow rounded text-sm">
      <thead class="bg-slate-100 text-left">
        <tr>
          <th class="p-2">单号</th><th class="p-2">日期</th><th class="p-2">分类</th>
          <th class="p-2">金额</th><th class="p-2">付款类型</th><th class="p-2">状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in items" :key="e.id" class="border-t">
          <td class="p-2"><RouterLink class="text-sky-700" :to="`/admin/expenses/${e.id}`">{{ e.claim_no }}</RouterLink></td>
          <td class="p-2">{{ e.expense_date }}</td>
          <td class="p-2">{{ e.category }}</td>
          <td class="p-2">{{ e.currency }} {{ e.amount_tax_included }}</td>
          <td class="p-2">{{ e.pay_type }}</td>
          <td class="p-2">{{ e.status }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
