<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { ledgerPath, errorText, exportLedger, statusLabels } from '@/api/ledger'
import { beijingToday } from '@/utils/expenseMoney'
const filters = reactive({ month: beijingToday().slice(0, 7), payer: '', category: '', keyword: '' })
const meta = ref<any>({ categories: [], payers: [] }), report = ref<any>(null), error = ref(''), busy = ref(false), exporting = ref(false)
let generation = 0
async function load() {
  const current = ++generation; busy.value = true
  try { const { data } = await api.get(ledgerPath + '/monthly', { params: filters }); if (current === generation) { report.value = data; error.value = '' } }
  catch (e) { if (current === generation) error.value = errorText(e) } finally { if (current === generation) busy.value = false }
}
onMounted(async () => { try { meta.value = (await api.get(ledgerPath + '/meta')).data; await load() } catch (e) { error.value = errorText(e) } })
watch(filters, load)
function previousMonth() { const [year, month] = beijingToday().slice(0, 7).split('-').map(Number); filters.month = `${month === 1 ? year! - 1 : year}-${String(month === 1 ? 12 : month! - 1).padStart(2, '0')}` }
async function exportAll() { exporting.value = true; try { await exportLedger(filters) } catch (e) { error.value = errorText(e) } finally { exporting.value = false } }
</script>
<template>
  <div class="space-y-5">
    <div class="page-toolbar"><h1 class="page-title">月度开支</h1><div class="page-toolbar-actions"><button class="btn-secondary" @click="filters.month = beijingToday().slice(0, 7)">本月</button><button class="btn-secondary" @click="previousMonth">上月</button><button class="btn-primary" :disabled="busy || exporting" @click="exportAll">{{ exporting ? '正在导出…' : '导出 Excel' }}</button></div></div>
    <div class="grid sm:grid-cols-4 gap-3"><label class="input-label">支出月份<input v-model="filters.month" type="month" class="input" required /></label><label class="input-label">付款人<input v-model="filters.payer" list="report-payers" class="input" placeholder="全部付款人" /><datalist id="report-payers"><option v-for="p in meta.payers" :key="p">{{ p }}</option></datalist></label><label class="input-label">分类<select v-model="filters.category" class="input"><option value="">全部分类</option><option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option></select></label><label class="input-label">关键词<input v-model="filters.keyword" class="input" placeholder="购买内容、商家、备注、付款人" /></label></div>
    <p v-if="error" class="alert-error">{{ error }}</p>
    <template v-if="report">
      <p v-if="report.unconfirmed_count" class="alert-warning">历史未核对记录未计入：{{ report.unconfirmed_count }} 笔。<RouterLink class="link" to="/admin/expenses/history">核对历史单据</RouterLink></p>
      <div class="stat-card"><p class="stat-label">{{ filters.month || '全部月份' }} 支出总额（人民币）</p><p class="stat-value">¥ {{ report.total_amount }}</p><p class="muted text-sm">{{ report.count }} 笔有效支出；年付全额计入支出月份，报销不增加费用。</p></div>
      <p class="text-sm muted">{{ report.scope }}。全部月份欠款请到 <RouterLink class="link" to="/admin/expenses">支出记录 → 待报销</RouterLink> 查看。</p>
      <h2 class="section-title">分类汇总</h2><div class="table-wrap"><table class="table"><thead><tr><th>分类</th><th>人民币金额</th><th>笔数</th></tr></thead><tbody><tr v-for="c in report.categories" :key="c.category"><td>{{ c.label }}</td><td>{{ c.amount }}</td><td>{{ c.count }}</td></tr></tbody></table></div>
      <h2 class="section-title">人员汇总（以支出月份为范围）</h2><div class="table-wrap"><table class="table"><thead><tr><th>付款人</th><th>需报销记账额</th><th>当前待报销额</th><th>已结清记账额</th><th>这些支出实际已报销额</th><th>差额</th><th>无需报销金额</th></tr></thead><tbody><tr v-for="p in report.people" :key="p.payer"><td>{{ p.payer }}</td><td>{{ p.required }}</td><td>{{ p.pending }}</td><td>{{ p.settled }}</td><td>{{ p.actual }}</td><td>{{ p.difference }}</td><td>{{ p.not_required }}</td></tr></tbody></table></div>
      <h2 class="section-title">支出明细（完整筛选结果）</h2><div class="table-wrap"><table class="table"><thead><tr><th>日期</th><th>购买内容</th><th>分类</th><th>商家</th><th>付款人</th><th>原币金额</th><th>人民币金额</th><th>状态</th><th>报销日期</th><th>备注</th></tr></thead><tbody><tr v-for="r in report.items" :key="r.id"><td>{{ r.expense_date }}</td><td><RouterLink class="link" :to="`/admin/expenses/${r.id}`">{{ r.title }}</RouterLink></td><td>{{ r.category_label }}</td><td>{{ r.merchant }}</td><td>{{ r.payer }}</td><td>{{ r.currency }} {{ r.amount }}</td><td>{{ r.rmb_amount }}</td><td>{{ statusLabels[r.status] }}</td><td>{{ r.reimbursement_date || '—' }}</td><td>{{ r.notes }}</td></tr></tbody></table></div>
    </template>
  </div>
</template>
