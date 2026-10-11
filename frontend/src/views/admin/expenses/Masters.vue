<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { errorText } from '@/api/ledger'
const suppliers = ref<any[]>([]), centers = ref<any[]>([]), accounts = ref<any[]>([]), error = ref('')
onMounted(async () => {
  try { const [s,c,a] = await Promise.all([api.get('/admin/suppliers'),api.get('/admin/cost-centers'),api.get('/admin/payment-accounts')]); suppliers.value=s.data; centers.value=c.data; accounts.value=a.data }
  catch (e) { error.value = errorText(e) }
})
</script>
<template><div class="space-y-4"><RouterLink class="link" to="/admin/expenses/history">← 返回历史单据</RouterLink><h1 class="page-title">历史主数据（只读）</h1><p class="muted">新支出无需预建供应商、成本中心或付款账户。原资料继续保留。</p><p v-if="error" class="alert-error">{{ error }}</p><div class="card card-body"><h2 class="section-title">供应商</h2><p v-for="s in suppliers" :key="s.id">{{ s.name }} · {{ s.supplier_type }}</p></div><div class="card card-body"><h2 class="section-title">成本中心</h2><p v-for="c in centers" :key="c.id">{{ c.code }} · {{ c.name }} · {{ c.enabled ? '启用' : '停用' }}</p></div><div class="card card-body"><h2 class="section-title">付款账户</h2><p v-for="a in accounts" :key="a.id">{{ a.name }} · {{ a.account_no_masked }} · {{ a.owner_label }}</p></div></div></template>
