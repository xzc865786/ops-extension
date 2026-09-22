<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const now = new Date()
const q = reactive({ period: 'month', year: now.getFullYear(), month: now.getMonth() + 1, currency: '' })
const availableCurrencies = ref<string[]>(['CNY', 'USD', 'HKD', 'EUR', 'JPY'])
const summary = ref<any>(null)
const dimensions = reactive<Record<string, any[]>>({ month: [], category: [], supplier: [], cost_center: [] })
const payment = ref<any>(null)
const invoice = ref<any>(null)
const exportView = ref('summary')
const viewOptions = [
  ['detail', '单据明细'], ['summary', '费用汇总'], ['month', '按月份'],
  ['category', '按分类'], ['supplier', '按供应商'], ['cost_center', '按成本中心'],
  ['payment', '付款状态'], ['invoice', '发票统计'],
]

function params() {
  return {
    period: q.period, year: q.year, month: q.period === 'month' ? q.month : undefined,
    currency: q.currency || undefined,
  }
}

async function load() {
  try {
    const names = ['summary', 'by-month', 'by-category', 'by-supplier', 'by-cost-center',
      'payment-status', 'invoice-tax']
    const responses = await Promise.all(names.map(name => api.get(`/admin/reports/${name}`, { params: params() })))
    summary.value = responses[0].data
    dimensions.month = responses[1].data
    dimensions.category = responses[2].data
    dimensions.supplier = responses[3].data
    dimensions.cost_center = responses[4].data
    payment.value = responses[5].data
    invoice.value = responses[6].data
  } catch (e: any) {
    toast.error(e.response?.data?.detail?.detail || e.response?.data?.detail || '报表加载失败')
  }
}

onMounted(async () => {
  try {
    const { data } = await api.get('/admin/expenses/meta')
    availableCurrencies.value = data.currencies
  } catch { /* report API still works without the selector metadata */ }
  await load()
})

function exportUrl(format: string, view: string) {
  const sp = new URLSearchParams({
    format, view, period: q.period, year: String(q.year),
    ...(q.period === 'month' ? { month: String(q.month) } : {}),
    ...(q.currency ? { currency: q.currency } : {}),
  })
  return `/ext/api/v1/admin/reports/export?${sp}`
}

function doExport(format: string, view: string) {
  const a = document.createElement('a')
  a.href = exportUrl(format, view)
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-end gap-3">
      <h1 class="page-title mr-auto">费用报表</h1>
      <select v-model="q.period" class="input"><option value="month">按月</option><option value="year">按年</option></select>
      <input v-model.number="q.year" type="number" class="input w-24" aria-label="年份" />
      <input v-if="q.period==='month'" v-model.number="q.month" type="number" min="1" max="12" class="input w-16" aria-label="月份" />
      <select v-model="q.currency" class="input" aria-label="币种">
        <option value="">全部币种（分别显示）</option>
        <option v-for="currency in availableCurrencies" :key="currency" :value="currency">{{ currency }}</option>
      </select>
      <button class="btn-primary" @click="load">查询</button>
    </div>
    <div class="flex flex-wrap gap-2 items-center">
      <select v-model="exportView" class="input" aria-label="CSV 报表类型">
        <option v-for="[value, label] in viewOptions" :key="value" :value="value">{{ label }}</option>
      </select>
      <button class="btn-secondary" @click="doExport('csv', exportView)">导出当前 CSV</button>
      <button class="btn-secondary" @click="doExport('xlsx', 'all')">导出完整 Excel</button>
    </div>

    <div v-for="group in summary?.currencies || []" :key="group.currency" class="card p-4 text-sm">
      <h2 class="font-medium">{{ group.currency }} 费用支出</h2>
      <p>已审批/已付 {{ group.count }} 笔 · {{ group.total_amount }} · 税额 {{ group.tax_amount }}</p>
      <p>待审批 {{ group.by_status.SUBMITTED?.count || 0 }} 笔 · {{ group.by_status.SUBMITTED?.amount || 0 }}</p>
      <p>已驳回 {{ group.by_status.REJECTED?.count || 0 }} 笔 · {{ group.by_status.REJECTED?.amount || 0 }}</p>
    </div>
    <p v-if="summary && !summary.currencies.length" class="muted text-sm">当前筛选条件下暂无数据</p>

    <div v-for="section in [
      { key: 'month', title: '按月份' }, { key: 'category', title: '按分类' },
      { key: 'supplier', title: '按供应商' }, { key: 'cost_center', title: '按成本中心' },
    ]" :key="section.key" class="card p-4">
      <h2 class="font-medium mb-2">{{ section.title }}</h2>
      <div class="table-wrap"><table class="table text-sm">
        <thead><tr><th>币种</th><th>{{ section.key === 'month' ? '月份' : '项目' }}</th><th>笔数</th><th>金额</th><th v-if="section.key === 'month'">税额</th></tr></thead>
        <tbody><tr v-for="(row, index) in dimensions[section.key]" :key="index">
          <td>{{ row.currency }}</td><td>{{ section.key === 'month' ? row.month : row.label }}</td>
          <td>{{ row.count }}</td><td>{{ row.amount }}</td><td v-if="section.key === 'month'">{{ row.tax_amount }}</td>
        </tr></tbody>
      </table></div>
      <p v-if="!dimensions[section.key].length" class="muted text-sm mt-2">暂无数据</p>
    </div>

    <div class="card p-4">
      <h2 class="font-medium mb-2">付款状态</h2>
      <div class="table-wrap"><table class="table text-sm">
        <thead><tr><th>币种</th><th>实际已付</th><th>已审批待付</th><th>已驳回金额</th><th>异常单据</th></tr></thead>
        <tbody><tr v-for="row in payment?.currencies || []" :key="row.currency">
          <td>{{ row.currency }}</td><td>{{ row.paid_amount }}</td><td>{{ row.unpaid_approved_amount }}</td>
          <td>{{ row.rejected_amount }}（{{ row.rejected_count }} 笔）</td>
          <td>{{ row.anomaly_count ? row.anomalies.join(', ') : '—' }}</td>
        </tr></tbody>
      </table></div>
      <p v-if="payment?.currencies?.some((row: any) => row.anomaly_count)" class="text-amber-300 text-sm mt-2">
        存在历史付款异常；异常单未计入已付和待付统计，须先核对后用于财务验收。
      </p>
    </div>

    <div class="card p-4">
      <h2 class="font-medium mb-2">发票统计</h2>
      <div class="table-wrap"><table class="table text-sm">
        <thead><tr><th>币种</th><th>有票金额</th><th>无票/待票金额</th><th>税额</th><th>预计可抵扣税额</th></tr></thead>
        <tbody><tr v-for="row in invoice?.currencies || []" :key="row.currency">
          <td>{{ row.currency }}</td><td>{{ row.with_invoice_amount }}</td><td>{{ row.without_invoice_amount }}</td>
          <td>{{ row.tax_amount }}</td><td>{{ row.deductible_tax }}</td>
        </tr></tbody>
      </table></div>
    </div>
  </div>
</template>
