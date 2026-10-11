<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { BATCH_LIMIT, emptyMeta, ledgerPath, statusLabels, errorText, type ExpenseRecord, type ListSummary, type PendingPayer } from '@/api/ledger'
import { RANGE_PRESETS, dateRangeLabel, dateRangeParams, isDateRange, type DateRange } from '@/utils/dateRange'
import { yuan } from '@/utils/expenseMoney'
import DateRangePicker from '@/components/DateRangePicker.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import ReimbursementForm from '@/components/expenses/ReimbursementForm.vue'
const route = useRoute()
// Report links pass their filters through the query string.
const q = (key: string) => typeof route.query[key] === 'string' ? route.query[key] as string : ''
const linkedRange = [q('date_from'), q('date_to')]
const initialRange = isDateRange(linkedRange) ? linkedRange : q('all_dates') ? null : RANGE_PRESETS[0]!.range()
const filters = reactive({ range: initialRange as DateRange | null, payer: q('payer'), category: q('category'), status: q('status'), keyword: q('keyword'), mine: false, voided: false })
// Free-text inputs settle for 300ms before they reach the filters.
const typed = reactive({ payer: filters.payer, keyword: filters.keyword })
let typing: ReturnType<typeof setTimeout> | undefined
watch(typed, () => { clearTimeout(typing); typing = setTimeout(() => Object.assign(filters, typed), 300) })
onBeforeUnmount(() => clearTimeout(typing))
const pendingView = computed(() => !filters.mine && filters.status === 'PENDING')
const moreOpen = ref(!!(filters.payer || filters.category || filters.status))
// The 待报销 tab sets status itself, so it is not counted as a hidden extra filter.
const extraCount = computed(() => [filters.payer, filters.category, !pendingView.value && filters.status, filters.voided].filter(Boolean).length)
const items = ref<ExpenseRecord[]>([]), total = ref(0), page = ref(1), selected = ref<number[]>([]), summary = ref<ListSummary | null>(null)
const meta = ref(emptyMeta()), error = ref(''), busy = ref(false), reimbursing = ref<ExpenseRecord[]>([])
const payers = ref<PendingPayer[]>([]), settling = ref('')
const selectedRows = computed(() => items.value.filter(r => selected.value.includes(r.id)))
const canBatch = computed(() => selectedRows.value.length > 0 && selectedRows.value.every(r => r.status === 'PENDING' && r.payer === selectedRows.value[0]!.payer))
let generation = 0
async function load() {
  const current = ++generation; busy.value = true; error.value = ''; selected.value = []
  try {
    const { range, ...rest } = filters
    const { data } = await api.get(ledgerPath, { params: { ...rest, ...dateRangeParams(range), status: filters.status || undefined, page: page.value, page_size: 20 } })
    if (current === generation) { items.value = data.items; total.value = data.total; summary.value = data.summary }
  } catch (e) { if (current === generation) error.value = errorText(e) } finally { if (current === generation) busy.value = false }
}
async function loadPayers() {
  try { payers.value = (await api.get(ledgerPath + '/pending-payers')).data } catch (e) { error.value = errorText(e) }
}
watch(filters, () => { selected.value = []; page.value = 1; reimbursing.value = []; void load() })
watch(page, () => { selected.value = []; reimbursing.value = []; void load() })
watch(pendingView, on => { if (on) void loadPayers() })
onMounted(async () => {
  try { meta.value = (await api.get(ledgerPath + '/meta')).data; await Promise.all([load(), pendingView.value ? loadPayers() : null]) } catch (e) { error.value = errorText(e) }
})
function quick(value: string) {
  filters.mine = value === 'mine'; filters.status = value === 'pending' ? 'PENDING' : ''; filters.voided = false
  if (value === 'pending') filters.range = null
}
async function settle(payer: PendingPayer) {
  if (settling.value) return
  settling.value = payer.payer; error.value = ''
  try {
    const { data } = await api.get<ExpenseRecord[]>(ledgerPath + '/pending', { params: { payer: payer.payer } })
    if (!data.length) { await loadPayers(); return }
    if (data.length > BATCH_LIMIT) { error.value = `${payer.payer} 有 ${data.length} 笔待报销，单次最多结清 ${BATCH_LIMIT} 笔。请按日期筛选后勾选分批登记。`; return }
    reimbursing.value = data
  } catch (e) { error.value = errorText(e) } finally { settling.value = '' }
}
async function done() { reimbursing.value = []; await Promise.all([load(), pendingView.value ? loadPayers() : null]) }
</script>
<template>
  <div class="space-y-5">
    <div class="page-toolbar !mb-0"><h1 class="page-title">支出记录</h1><div class="page-toolbar-actions"><RouterLink class="btn-primary" to="/admin/expenses/new">记一笔</RouterLink></div></div>
    <div class="tabs w-fit" role="group" aria-label="快捷查看">
      <button type="button" class="tab" :class="{ 'tab-active': !filters.mine && !filters.status }" :aria-pressed="!filters.mine && !filters.status" @click="quick('all')">全部</button>
      <button type="button" class="tab" :class="{ 'tab-active': pendingView }" :aria-pressed="pendingView" @click="quick('pending')">待报销</button>
      <button type="button" class="tab" :class="{ 'tab-active': filters.mine }" :aria-pressed="filters.mine" @click="quick('mine')">我录入的</button>
    </div>
    <div class="ledger-filters grid sm:grid-cols-2 xl:grid-cols-4 gap-3 items-end">
      <div class="ledger-filter sm:col-span-2"><span class="input-label !mb-0">支出日期</span><DateRangePicker v-model="filters.range" allow-all aria-label="支出日期范围" /></div>
      <label class="ledger-filter"><span class="input-label !mb-0">关键词</span><input v-model="typed.keyword" class="input" placeholder="内容、商家、备注、付款人" /></label>
      <div class="ledger-filter"><button type="button" class="btn-secondary h-11 w-fit" :aria-expanded="moreOpen" aria-controls="more-filters" @click="moreOpen = !moreOpen">{{ moreOpen ? '收起筛选' : '更多筛选' }}<span v-if="extraCount" class="badge-primary">{{ extraCount }}</span></button></div>
    </div>
    <div v-if="moreOpen" id="more-filters" class="ledger-filters grid sm:grid-cols-2 xl:grid-cols-4 gap-3 items-end">
      <label class="ledger-filter"><span class="input-label !mb-0">付款人</span><input v-model="typed.payer" list="list-payers" class="input" placeholder="全部付款人" /><datalist id="list-payers"><option v-for="p in meta.payers" :key="p">{{ p }}</option></datalist></label>
      <label class="ledger-filter"><span class="input-label !mb-0">分类</span><select v-model="filters.category" class="input"><option value="">全部分类</option><option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option></select></label>
      <label class="ledger-filter"><span class="input-label !mb-0">报销状态</span><select v-model="filters.status" class="input"><option value="">全部状态</option><option v-for="s in ['PENDING', 'REIMBURSED', 'NOT_REQUIRED']" :key="s" :value="s">{{ statusLabels[s] }}</option></select></label>
      <label class="ledger-filter flex-row items-center gap-2 h-11"><input v-model="filters.voided" type="checkbox" />仅查看作废记录</label>
    </div>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p>
    <section v-if="pendingView" class="space-y-3" aria-label="按付款人结清">
      <h2 class="section-title">按付款人结清 <span class="text-sm font-normal muted">（全部日期）</span></h2>
      <p v-if="!payers.length" class="empty-state !py-6">目前没有待报销的垫付。</p>
      <div v-else class="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
        <div v-for="p in payers" :key="p.payer" class="card p-4 flex items-center gap-3">
          <div class="min-w-0 flex-1"><p class="font-medium truncate">{{ p.payer }}</p><p class="text-sm muted">{{ p.count }} 笔 · <span class="tabular-nums font-semibold text-gray-900 dark:text-white">{{ yuan(p.amount) }}</span></p></div>
          <button type="button" class="btn-primary btn-sm" :disabled="!!settling || !!reimbursing.length" :aria-label="`结清 ${p.payer} 的 ${p.count} 笔待报销`" @click="settle(p)">{{ settling === p.payer ? '读取中…' : '结清' }}</button>
        </div>
      </div>
    </section>
    <ReimbursementForm v-if="reimbursing.length" :key="reimbursing.map(r => r.id).join(',')" :records="reimbursing" @done="done" @cancel="reimbursing = []" />
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      <span v-if="summary">共 <b class="tabular-nums">{{ summary.count }}</b> 笔 · 合计 <b class="tabular-nums">{{ yuan(summary.total_amount) }}</b><template v-if="!filters.voided"> · 其中待报销 <b class="tabular-nums">{{ yuan(summary.pending_amount) }}</b></template></span>
      <span class="muted">{{ dateRangeLabel(filters.range) }}（按支出日期）</span>
      <template v-if="selected.length">
        <button class="btn-secondary btn-sm" :disabled="!canBatch || busy" @click="reimbursing = selectedRows">合并报销所选 {{ selected.length }} 笔</button>
        <span v-if="!canBatch" class="muted">需为同一付款人的待报销记录</span>
      </template>
    </div>
    <div class="table-wrap" :aria-busy="busy"><table class="table"><thead><tr><th><span class="sr-only">选择</span></th><th>支出日期</th><th>买了什么</th><th>分类</th><th>付款人</th><th class="!text-right">美元金额</th><th class="!text-right">折合人民币</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="r in items" :key="r.id">
          <td><input v-model="selected" :value="r.id" type="checkbox" :disabled="busy || r.status !== 'PENDING'" :aria-label="`选择支出 ${r.id}`" /></td>
          <td class="tabular-nums">{{ r.expense_date }}</td>
          <td class="max-w-xs"><RouterLink :to="`/admin/expenses/${r.id}`" class="link block truncate">{{ r.title }}</RouterLink><span v-if="r.merchant" class="block text-xs muted truncate">{{ r.merchant }}</span></td>
          <td>{{ r.category_label }}</td><td>{{ r.payer }}</td>
          <td class="text-right tabular-nums">{{ r.currency === 'USD' ? `$ ${r.amount}` : '—' }}</td>
          <td class="text-right tabular-nums font-medium">{{ yuan(r.rmb_amount) }}</td>
          <td><StatusBadge kind="ledger" :status="r.status" /></td>
          <td><div class="flex gap-3"><RouterLink :to="`/admin/expenses/new?copy=${r.id}`" class="link">复制一笔</RouterLink><button v-if="r.status === 'PENDING'" type="button" class="link" @click="reimbursing = [r]">报销</button></div></td>
        </tr>
        <tr v-if="!items.length"><td colspan="9" class="text-center muted">{{ busy ? '正在读取…' : '没有符合条件的记录' }}</td></tr>
      </tbody>
    </table></div>
    <div class="flex flex-wrap items-center gap-3"><span>共 {{ total }} 条，第 {{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }} 页</span><button class="btn-secondary" :disabled="page <= 1 || busy" @click="page--">上一页</button><button class="btn-secondary" :disabled="page * 20 >= total || busy" @click="page++">下一页</button></div>
  </div>
</template>
