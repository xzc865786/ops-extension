<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { emptyMeta, ledgerPath, errorText, exportLedger } from '@/api/ledger'
import { RANGE_PRESETS, dateRangeLabel, dateRangeParams, type DateRange } from '@/utils/dateRange'
import { money, signedCents, yuan } from '@/utils/expenseMoney'
import DateRangePicker from '@/components/DateRangePicker.vue'
import StatusBadge from '@/components/StatusBadge.vue'
const filters = reactive({ range: RANGE_PRESETS[0]!.range() as DateRange | null, payer: '', category: '', keyword: '' })
const typed = reactive({ payer: '', keyword: '' })
let typing: ReturnType<typeof setTimeout> | undefined
watch(typed, () => { clearTimeout(typing); typing = setTimeout(() => Object.assign(filters, typed), 300) })
onBeforeUnmount(() => clearTimeout(typing))
function queryParams() { const { range, ...rest } = filters; return { ...rest, ...dateRangeParams(range) } }
const meta = ref(emptyMeta()), report = ref<any>(null), error = ref(''), busy = ref(false), exporting = ref(false)
let generation = 0
async function load() {
  const current = ++generation; busy.value = true
  try { const { data } = await api.get(ledgerPath + '/monthly', { params: queryParams() }); if (current === generation) { report.value = data; error.value = '' } }
  catch (e) { if (current === generation) error.value = errorText(e) } finally { if (current === generation) busy.value = false }
}
onMounted(async () => { try { meta.value = (await api.get(ledgerPath + '/meta')).data; await load() } catch (e) { error.value = errorText(e) } })
watch(filters, load)
async function exportAll() { exporting.value = true; try { await exportLedger(queryParams()) } catch (e) { error.value = errorText(e) } finally { exporting.value = false } }
// Percentages are display-only; amounts themselves stay exact decimal strings.
const change = computed(() => {
  const previous = report.value?.previous_total_amount
  if (previous == null) return null
  const now = signedCents(report.value.total_amount), before = signedCents(previous)
  const diff = now - before
  return { diff: money(diff), up: diff > 0n, percent: before === 0n ? null : Math.abs(Number(diff) / Number(before) * 100).toFixed(1) }
})
const categories = computed(() => {
  const total = Number(signedCents(report.value?.total_amount || '0'))
  return [...(report.value?.categories || [])].sort((a, b) => Number(signedCents(b.amount) - signedCents(a.amount)))
    .map(c => ({ ...c, share: total ? Number(signedCents(c.amount)) / total * 100 : 0 }))
})
const people = computed(() => (report.value?.people || []).filter((p: any) => signedCents(p.required) !== 0n))
const companyPaid = computed(() => money((report.value?.people || []).reduce((sum: bigint, p: any) => sum + signedCents(p.not_required), 0n)))
const listLink = computed(() => {
  const { range, ...rest } = filters
  const query: Record<string, string> = Object.fromEntries(Object.entries(rest).filter(([, v]) => v))
  return { path: '/admin/expenses', query: range ? { ...query, date_from: range[0], date_to: range[1] } : { ...query, all_dates: '1' } }
})
</script>
<template>
  <div class="space-y-5">
    <div class="page-toolbar !mb-0"><h1 class="page-title">月度开支</h1><div class="page-toolbar-actions"><button class="btn-primary" :disabled="busy || exporting" @click="exportAll">{{ exporting ? '正在导出…' : '导出 Excel' }}</button></div></div>
    <div class="ledger-filters grid sm:grid-cols-2 xl:grid-cols-5 gap-3">
      <div class="ledger-filter sm:col-span-2"><span class="input-label !mb-0">支出日期</span><DateRangePicker v-model="filters.range" allow-all aria-label="支出日期范围" /></div>
      <label class="ledger-filter"><span class="input-label !mb-0">付款人</span><input v-model="typed.payer" list="report-payers" class="input" placeholder="全部付款人" /><datalist id="report-payers"><option v-for="p in meta.payers" :key="p">{{ p }}</option></datalist></label>
      <label class="ledger-filter"><span class="input-label !mb-0">分类</span><select v-model="filters.category" class="input"><option value="">全部分类</option><option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option></select></label>
      <label class="ledger-filter"><span class="input-label !mb-0">关键词</span><input v-model="typed.keyword" class="input" placeholder="购买内容、商家、备注、付款人" /></label>
    </div>
    <p v-if="error" class="alert-error">{{ error }}</p>
    <template v-if="report">
      <div class="grid sm:grid-cols-3 gap-3">
        <div class="stat-card"><p class="stat-label">本期总支出</p><p class="stat-value">{{ yuan(report.total_amount) }}</p><p class="muted text-sm">{{ dateRangeLabel(filters.range) }} · {{ report.count }} 笔</p></div>
        <div class="stat-card"><p class="stat-label">其中待报销</p><p class="stat-value">{{ yuan(report.pending_amount) }}</p><p class="muted text-sm">这些支出里尚未还给垫付人的部分</p></div>
        <div class="stat-card"><p class="stat-label">比上期</p>
          <template v-if="change"><p class="stat-value" :class="change.up ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'">{{ change.up ? '+' : '' }}{{ yuan(change.diff) }}</p><p class="muted text-sm">{{ change.percent == null ? '上期没有支出' : `${change.up ? '增加' : '减少'} ${change.percent}%` }} · 上期 {{ report.previous_range.join(' ~ ') }} {{ yuan(report.previous_total_amount) }}</p></template>
          <template v-else><p class="stat-value">—</p><p class="muted text-sm">选择日期范围后对比上期</p></template>
        </div>
      </div>
      <p class="text-sm muted">年付全额计入支出日期，报销不增加费用。全部月份欠款请到 <RouterLink class="link" :to="{ path: '/admin/expenses', query: { status: 'PENDING', all_dates: '1' } }">支出记录 → 待报销</RouterLink> 查看。</p>
      <section class="space-y-3"><h2 class="section-title">钱花在哪</h2>
        <p v-if="!categories.length" class="empty-state !py-6">所选范围内没有支出。</p>
        <div v-else class="card card-body space-y-3">
          <div v-for="c in categories" :key="c.category" class="grid grid-cols-[6rem_1fr_auto] sm:grid-cols-[8rem_1fr_9rem] items-center gap-3 text-sm">
            <span class="truncate">{{ c.label }}</span>
            <div class="h-2.5 rounded-full bg-gray-100 dark:bg-dark-700 overflow-hidden" role="img" :aria-label="`${c.label}占 ${c.share.toFixed(1)}%`"><div class="h-full rounded-full bg-primary-500" :style="{ width: `${Math.max(c.share, 1)}%` }" /></div>
            <span class="text-right tabular-nums"><b>{{ yuan(c.amount) }}</b> <span class="muted">{{ c.share.toFixed(0) }}% · {{ c.count }} 笔</span></span>
          </div>
        </div>
      </section>
      <section class="space-y-3"><h2 class="section-title">垫付与报销 <span class="text-sm font-normal muted">（按所选支出日期）</span></h2>
        <div class="table-wrap"><table class="table"><thead><tr><th>付款人</th><th class="!text-right">垫付合计</th><th class="!text-right">已报销</th><th class="!text-right">待报销</th></tr></thead><tbody>
          <tr v-for="p in people" :key="p.payer"><td>{{ p.payer }}</td><td class="text-right tabular-nums">{{ yuan(p.required) }}</td>
            <td class="text-right tabular-nums">{{ yuan(p.actual) }}<span v-if="signedCents(p.difference) !== 0n" class="block text-xs text-amber-600 dark:text-amber-400">实报比记账{{ signedCents(p.difference) < 0n ? '少' : '多' }} {{ yuan(money(signedCents(p.difference) < 0n ? -signedCents(p.difference) : signedCents(p.difference))) }}</span></td>
            <td class="text-right tabular-nums font-medium" :class="{ 'text-amber-600 dark:text-amber-400': signedCents(p.pending) > 0n }">{{ yuan(p.pending) }}</td></tr>
          <tr v-if="signedCents(companyPaid) !== 0n"><td>公司直付 <span class="text-xs muted">（无需报销）</span></td><td class="text-right tabular-nums">{{ yuan(companyPaid) }}</td><td class="text-right muted">—</td><td class="text-right muted">—</td></tr>
          <tr v-if="!people.length && signedCents(companyPaid) === 0n"><td colspan="4" class="text-center muted">所选范围内没有支出</td></tr>
        </tbody></table></div>
        <p class="text-xs muted">已报销为这些支出实际还给垫付人的金额，不是所选期间发生的转账流水。完整对账列见导出的“人员汇总”表。</p>
      </section>
      <details class="space-y-3">
        <summary class="cursor-pointer section-title w-fit">支出明细（{{ report.count }} 笔）</summary>
        <p class="mt-3 text-sm"><RouterLink class="link" :to="listLink">在支出记录中查看和操作这些支出 →</RouterLink></p>
        <div class="table-wrap mt-3"><table class="table"><thead><tr><th>日期</th><th>购买内容</th><th>分类</th><th>付款人</th><th class="!text-right">人民币金额</th><th>状态</th><th>报销日期</th></tr></thead><tbody><tr v-for="r in report.items" :key="r.id"><td class="tabular-nums">{{ r.expense_date }}</td><td><RouterLink class="link" :to="`/admin/expenses/${r.id}`">{{ r.title }}</RouterLink></td><td>{{ r.category_label }}</td><td>{{ r.payer }}</td><td class="text-right tabular-nums">{{ yuan(r.rmb_amount) }}</td><td><StatusBadge kind="ledger" :status="r.status" /></td><td>{{ r.reimbursement_date || '—' }}</td></tr></tbody></table></div>
      </details>
    </template>
  </div>
</template>
