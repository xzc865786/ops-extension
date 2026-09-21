<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const now = new Date()
const q = reactive({ period: 'month', year: now.getFullYear(), month: now.getMonth() + 1 })
const summary = ref<any>(null)
const byCategory = ref<any[]>([])
const payment = ref<any>(null)
const invoice = ref<any>(null)

async function load() {
  const params = { ...q }
  try {
    const [s, c, p, i] = await Promise.all([
      api.get('/admin/reports/summary', { params }),
      api.get('/admin/reports/by-category', { params }),
      api.get('/admin/reports/payment-status', { params }),
      api.get('/admin/reports/invoice-tax', { params }),
    ])
    summary.value = s.data
    byCategory.value = c.data
    payment.value = p.data
    invoice.value = i.data
  } catch (e: any) {
    toast.error(e.response?.data?.detail?.detail || e.response?.data?.detail || '报表加载失败')
  }
}
onMounted(load)

function exportUrl(format: string) {
  const sp = new URLSearchParams({
    format,
    period: q.period,
    year: String(q.year),
    ...(q.period === 'month' ? { month: String(q.month) } : {}),
  })
  return `/ext/api/v1/admin/reports/export?${sp}`
}

function doExport(format: string) {
  try {
    const url = exportUrl(format)
    const a = document.createElement('a')
    a.href = url
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    toast.success(format === 'xlsx' ? '已开始导出 Excel' : '已开始导出 CSV')
  } catch {
    toast.error('导出失败，请重试')
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-end gap-3">
      <h1 class="page-title mr-auto">费用报表</h1>
      <select v-model="q.period" class="input">
        <option value="month">按月</option>
        <option value="year">按年</option>
      </select>
      <input v-model.number="q.year" type="number" class="input w-24" />
      <input v-if="q.period==='month'" v-model.number="q.month" type="number" min="1" max="12" class="input w-16" />
      <button type="button" class="btn-primary" @click="load">查询</button>
      <button type="button" class="btn-secondary" @click="doExport('csv')">导出 CSV</button>
      <button type="button" class="btn-secondary" @click="doExport('xlsx')">导出 Excel</button>
    </div>

    <div v-if="summary" class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="card p-3">
        <div class="text-xs muted">单据数</div>
        <div class="text-2xl font-semibold">{{ summary.count }}</div>
      </div>
      <div class="card p-3">
        <div class="text-xs muted">合计金额</div>
        <div class="text-2xl font-semibold">{{ summary.total_amount }}</div>
      </div>
      <div v-if="payment" class="card p-3">
        <div class="text-xs muted">已付</div>
        <div class="text-2xl font-semibold">{{ payment.paid.amount }}</div>
      </div>
      <div v-if="payment" class="card p-3">
        <div class="text-xs muted">已审批未付</div>
        <div class="text-2xl font-semibold">{{ payment.unpaid_approved.amount }}</div>
      </div>
    </div>

    <div class="card p-4">
      <h2 class="font-medium mb-2">按分类</h2>
      <div class="table-wrap"><table class="table">
        <thead><tr class="text-left muted"><th class="py-1">分类</th><th>笔数</th><th>金额</th></tr></thead>
        <tbody>
          <tr v-for="r in byCategory" :key="r.key" class="border-t">
            <td class="py-1">{{ r.label }}</td><td>{{ r.count }}</td><td>{{ r.amount }}</td>
          </tr>
        </tbody>
      </table></div>
      <p v-if="!byCategory.length" class="text-sm muted mt-2">当前周期暂无分类数据</p>
    </div>

    <div v-if="invoice" class="card p-4 text-sm grid grid-cols-2 gap-4">
      <div>
        <h3 class="font-medium">有票</h3>
        <p>金额 {{ invoice.with_invoice.amount }} · 税额 {{ invoice.with_invoice.tax_amount }} · 可抵扣 {{ invoice.with_invoice.deductible_tax }}</p>
      </div>
      <div>
        <h3 class="font-medium">无票/待票</h3>
        <p>金额 {{ invoice.without_invoice.amount }}</p>
      </div>
    </div>
    <p class="text-xs muted">V1 不含折旧与自动报税。</p>
  </div>
</template>
