<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'

const items = ref<any[]>([])
const status = ref('')
const payTypeLabel: Record<string, string> = {
  COMPANY_DIRECT: '公司直付',
  PERSONAL_ADVANCE: '个人垫付',
}

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
    <div class="page-toolbar">
      <h1 class="page-title shell-page-title">报账管理</h1>
      <div class="page-toolbar-actions">
        <RouterLink to="/admin/suppliers" class="btn-secondary">主数据</RouterLink>
        <RouterLink to="/admin/expenses/new" class="btn-primary">新建报账</RouterLink>
      </div>
    </div>
    <div class="filter-bar">
      <select v-model="status" class="input" aria-label="报账状态" @change="load">
        <option value="">全部状态</option>
        <option value="DRAFT">草稿</option><option value="SUBMITTED">待审批</option><option value="APPROVED">已审批</option>
        <option value="REJECTED">已驳回</option><option value="PAID">已付款</option><option value="CANCELLED">已取消</option>
      </select>
    </div>
    <div class="table-wrap"><table class="table">
      <thead class="text-left">
        <tr>
          <th class="p-2">单号</th><th class="p-2">日期</th><th class="p-2">分类</th>
          <th class="p-2">金额</th><th class="p-2">付款类型</th><th class="p-2">状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in items" :key="e.id">
          <td class="p-2"><RouterLink class="link" :to="`/admin/expenses/${e.id}`">{{ e.claim_no }}</RouterLink></td>
          <td class="p-2">{{ e.expense_date }}</td>
          <td class="p-2">{{ e.category }}</td>
          <td class="p-2">{{ e.currency }} {{ e.amount_tax_included }}</td>
          <td class="p-2">{{ payTypeLabel[e.pay_type] || e.pay_type }}</td>
          <td class="p-2"><StatusBadge :status="e.status" kind="expense" /></td>
        </tr>
        <tr v-if="!items.length"><td colspan="6" class="p-8 text-center muted">暂无报账单</td></tr>
      </tbody>
    </table></div>
  </div>
</template>
