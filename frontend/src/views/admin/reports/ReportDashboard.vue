<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import api from '@/api/client'
import DateRangePicker from '@/components/DateRangePicker.vue'
import { useToast } from '@/composables/useToast'
import { RANGE_PRESETS, isDateRange, presetFor, type DateRange } from '@/utils/dateRange'
import { labelFor, type LabelOption } from '@/utils/display'

const RANGE_STORAGE_KEY = 'ops-ext:report-range'

// A remembered preset is re-resolved against today, so "上月" stays relative across visits.
function initialRange(): DateRange {
  try {
    const saved = JSON.parse(localStorage.getItem(RANGE_STORAGE_KEY) || 'null')
    const preset = RANGE_PRESETS.find(p => p.key === saved?.preset)
    if (preset) return preset.range()
    if (isDateRange(saved?.range)) return saved.range
  } catch { /* storage unavailable or corrupt: fall back to the default */ }
  return RANGE_PRESETS[0].range()
}

function rememberRange(range: DateRange) {
  const preset = presetFor(range)
  try {
    localStorage.setItem(RANGE_STORAGE_KEY, JSON.stringify(preset ? { preset: preset.key } : { range }))
  } catch { /* remembering is a convenience only */ }
}

const toast = useToast()
const q = reactive({ range: initialRange(), currency: '' })
const availableCurrencies = ref<string[]>(['CNY', 'USD', 'HKD', 'EUR', 'JPY'])
const categories = ref<LabelOption[]>([])
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
  return { start_date: q.range[0], end_date: q.range[1], currency: q.currency || undefined }
}

const loading = ref(false)
let loadSeq = 0

async function load() {
  // Only the latest request may write results, so a slow earlier query can't overwrite a newer range.
  const seq = ++loadSeq
  loading.value = true
  try {
    const names = ['summary', 'by-month', 'by-category', 'by-supplier', 'by-cost-center',
      'payment-status', 'invoice-tax']
    const responses = await Promise.all(names.map(name => api.get(`/admin/reports/${name}`, { params: params() })))
    if (seq !== loadSeq) return
    summary.value = responses[0].data
    dimensions.month = responses[1].data
    dimensions.category = responses[2].data
    dimensions.supplier = responses[3].data
    dimensions.cost_center = responses[4].data
    payment.value = responses[5].data
    invoice.value = responses[6].data
  } catch (e: any) {
    if (seq === loadSeq) toast.error(e.response?.data?.detail?.detail || e.response?.data?.detail || '报表加载失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

watch(() => q.range, rememberRange)
watch(() => [q.range, q.currency], load)

onMounted(async () => {
  try {
    const { data } = await api.get('/admin/expenses/meta')
    availableCurrencies.value = data.currencies
    categories.value = data.categories
  } catch { /* report API still works without the selector metadata */ }
  await load()
})

function exportUrl(format: string, view: string) {
  const sp = new URLSearchParams({
    format, view, start_date: q.range[0], end_date: q.range[1],
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
    <div class="page-toolbar">
      <h1 class="page-title shell-page-title">费用报表</h1>
      <div class="page-toolbar-actions">
        <DateRangePicker v-model="q.range" aria-label="费用发生日期区间" />
        <select v-model="q.currency" class="input" aria-label="币种">
          <option value="">全部币种（分别显示）</option>
          <option v-for="currency in availableCurrencies" :key="currency" :value="currency">{{ currency }}</option>
        </select>
        <button class="btn-secondary" :disabled="loading" @click="load">{{ loading ? '加载中…' : '刷新' }}</button>
      </div>
    </div>
    <div class="filter-bar">
      <select v-model="exportView" class="input" aria-label="CSV 报表类型">
        <option v-for="[value, label] in viewOptions" :key="value" :value="value">{{ label }}</option>
      </select>
      <button class="btn-secondary" @click="doExport('csv', exportView)">导出当前 CSV</button>
      <button class="btn-secondary" @click="doExport('xlsx', 'all')">导出完整 Excel</button>
    </div>

    <div v-for="group in summary?.currencies || []" :key="group.currency" class="stat-card">
      <p class="stat-label">{{ group.currency }} 费用支出 · 已审批/已付 {{ group.count }} 笔</p>
      <p class="stat-value">{{ group.total_amount }}</p>
      <p class="mt-2 text-sm muted">税额 {{ group.tax_amount }}</p>
      <p class="mt-3 text-sm muted">待审批 {{ group.by_status.SUBMITTED?.count || 0 }} 笔 · {{ group.by_status.SUBMITTED?.amount || 0 }}</p>
      <p class="text-sm muted">已驳回 {{ group.by_status.REJECTED?.count || 0 }} 笔 · {{ group.by_status.REJECTED?.amount || 0 }}</p>
    </div>
    <p v-if="summary && !summary.currencies.length" class="empty-state">当前筛选条件下暂无数据</p>

    <div v-for="section in [
      { key: 'month', title: '按月份' }, { key: 'category', title: '按分类' },
      { key: 'supplier', title: '按供应商' }, { key: 'cost_center', title: '按成本中心' },
    ]" :key="section.key" class="card p-5 sm:p-6">
      <h2 class="section-title mb-3">{{ section.title }}</h2>
      <div class="table-wrap"><table class="table text-sm">
        <thead><tr><th>币种</th><th>{{ section.key === 'month' ? '月份' : '项目' }}</th><th>笔数</th><th>金额</th><th v-if="section.key === 'month'">税额</th></tr></thead>
        <tbody><tr v-for="(row, index) in dimensions[section.key]" :key="index">
          <td>{{ row.currency }}</td><td>{{ section.key === 'month' ? row.month : section.key === 'category' ? labelFor(categories, row.key) : row.label }}</td>
          <td>{{ row.count }}</td><td>{{ row.amount }}</td><td v-if="section.key === 'month'">{{ row.tax_amount }}</td>
        </tr></tbody>
      </table></div>
      <p v-if="!dimensions[section.key].length" class="empty-state mt-3">暂无数据</p>
    </div>

    <div class="card p-5 sm:p-6">
      <h2 class="section-title mb-3">付款状态</h2>
      <div class="table-wrap"><table class="table text-sm">
        <thead><tr><th>币种</th><th>实际已付</th><th>已审批待付</th><th>已驳回金额</th><th>异常单据</th></tr></thead>
        <tbody><tr v-for="row in payment?.currencies || []" :key="row.currency">
          <td>{{ row.currency }}</td><td>{{ row.paid_amount }}</td><td>{{ row.unpaid_approved_amount }}</td>
          <td>{{ row.rejected_amount }}（{{ row.rejected_count }} 笔）</td>
          <td>{{ row.anomaly_count ? row.anomalies.join(', ') : '—' }}</td>
        </tr>
        <tr v-if="payment && !payment.currencies?.length"><td colspan="5" class="p-8 text-center muted">暂无数据</td></tr>
        </tbody>
      </table></div>
      <p v-if="payment?.currencies?.some((row: any) => row.anomaly_count)" class="alert-warning mt-3">
        存在历史付款异常；异常单未计入已付和待付统计，须先核对后用于财务验收。
      </p>
    </div>

    <div class="card p-5 sm:p-6">
      <h2 class="section-title mb-3">发票统计</h2>
      <div class="table-wrap"><table class="table text-sm">
        <thead><tr><th>币种</th><th>有票金额</th><th>无票/待票金额</th><th>税额</th><th>预计可抵扣税额</th></tr></thead>
        <tbody><tr v-for="row in invoice?.currencies || []" :key="row.currency">
          <td>{{ row.currency }}</td><td>{{ row.with_invoice_amount }}</td><td>{{ row.without_invoice_amount }}</td>
          <td>{{ row.tax_amount }}</td><td>{{ row.deductible_tax }}</td>
        </tr>
        <tr v-if="invoice && !invoice.currencies?.length"><td colspan="5" class="p-8 text-center muted">暂无数据</td></tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>
