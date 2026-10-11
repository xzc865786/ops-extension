<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { ledgerPath, statusLabels, errorText, type ExpenseRecord } from '@/api/ledger'
import { RANGE_PRESETS, dateRangeLabel, dateRangeParams, type DateRange } from '@/utils/dateRange'
import DateRangePicker from '@/components/DateRangePicker.vue'
import ReimbursementForm from '@/components/expenses/ReimbursementForm.vue'
const filters = reactive({ range: RANGE_PRESETS[0]!.range() as DateRange | null, payer: '', category: '', status: '', keyword: '', mine: false, voided: false })
const items = ref<ExpenseRecord[]>([]), total = ref(0), page = ref(1), selected = ref<number[]>([])
const meta = ref<any>({ categories: [], payers: [] }), error = ref(''), busy = ref(false), reimbursing = ref<ExpenseRecord[]>([])
const selectedRows = computed(() => items.value.filter(r => selected.value.includes(r.id)))
const canBatch = computed(() => selectedRows.value.length > 0 && selectedRows.value.every(r => r.status === 'PENDING' && r.payer === selectedRows.value[0]!.payer))
let generation = 0
async function load() {
  const current = ++generation; busy.value = true; error.value = ''; selected.value = []
  try {
    const { range, ...rest } = filters
    const { data } = await api.get(ledgerPath, { params: { ...rest, ...dateRangeParams(range), status: filters.status || undefined, page: page.value, page_size: 20 } })
    if (current === generation) { items.value = data.items; total.value = data.total }
  } catch (e) { if (current === generation) error.value = errorText(e) } finally { if (current === generation) busy.value = false }
}
watch(filters, () => { selected.value = []; page.value = 1; reimbursing.value = []; void load() })
watch(page, () => { selected.value = []; reimbursing.value = []; void load() })
onMounted(async () => { try { meta.value = (await api.get(ledgerPath + '/meta')).data; await load() } catch (e) { error.value = errorText(e) } })
function quick(value: string) { filters.mine = value === 'mine'; filters.status = value === 'pending' ? 'PENDING' : ''; filters.voided = false; if (value === 'pending') filters.range = null }
async function voidRow(row: ExpenseRecord) {
  const reason = window.prompt('填写作废原因，原记录与凭证会保留')
  if (!reason?.trim()) return
  try { await api.post(`${ledgerPath}/${row.id}/void`, { version: row.version, reason }); await load() } catch (e) { error.value = errorText(e) }
}
async function done() { reimbursing.value = []; await load() }
</script>
<template>
  <div class="space-y-5">
    <div class="page-toolbar"><h1 class="page-title">支出记录</h1><div class="page-toolbar-actions"><RouterLink class="btn-primary" to="/admin/expenses/new">记一笔</RouterLink></div></div>
    <div class="flex flex-wrap gap-2"><button :class="!filters.mine && !filters.status ? 'btn-primary' : 'btn-secondary'" :aria-pressed="!filters.mine && !filters.status" @click="quick('all')">全部</button><button :class="!filters.mine && filters.status === 'PENDING' ? 'btn-primary' : 'btn-secondary'" :aria-pressed="!filters.mine && filters.status === 'PENDING'" @click="quick('pending')">待报销</button><button :class="filters.mine ? 'btn-primary' : 'btn-secondary'" :aria-pressed="filters.mine" @click="quick('mine')">我录入的</button></div>
    <div class="ledger-filters grid sm:grid-cols-2 xl:grid-cols-6 gap-3">
      <div class="ledger-filter sm:col-span-2"><span class="input-label !mb-0">支出日期</span><DateRangePicker v-model="filters.range" allow-all aria-label="支出日期范围" /></div>
      <label class="ledger-filter"><span class="input-label !mb-0">付款人</span><input v-model="filters.payer" list="list-payers" class="input" placeholder="全部付款人" /><datalist id="list-payers"><option v-for="p in meta.payers" :key="p">{{ p }}</option></datalist></label>
      <label class="ledger-filter"><span class="input-label !mb-0">分类</span><select v-model="filters.category" class="input"><option value="">全部分类</option><option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option></select></label>
      <label class="ledger-filter"><span class="input-label !mb-0">报销状态</span><select v-model="filters.status" class="input"><option value="">全部状态</option><option v-for="s in ['PENDING', 'REIMBURSED', 'NOT_REQUIRED']" :key="s" :value="s">{{ statusLabels[s] }}</option></select></label>
      <label class="ledger-filter"><span class="input-label !mb-0">关键词</span><input v-model="filters.keyword" class="input" placeholder="内容、商家、备注、付款人" /></label>
    </div>
    <div class="flex flex-wrap items-center gap-3 text-sm"><span>日期范围：{{ dateRangeLabel(filters.range) }}（按支出日期）</span><label class="flex items-center gap-2"><input v-model="filters.voided" type="checkbox" />仅查看作废记录</label><button class="btn-secondary" :disabled="!canBatch || busy" @click="reimbursing = selectedRows">合并报销当前页所选 {{ selected.length }} 笔</button><span class="muted">需为同一付款人的待报销记录</span></div>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p>
    <ReimbursementForm v-if="reimbursing.length" :key="reimbursing.map(r => r.id).join(',')" :records="reimbursing" @done="done" @cancel="reimbursing = []" />
    <div class="table-wrap" :aria-busy="busy"><table class="table"><thead><tr><th>选择</th><th>支出日期</th><th>买了什么</th><th>分类</th><th>付款人</th><th>原币金额</th><th>折合人民币</th><th>报销状态</th><th>操作</th></tr></thead>
      <tbody><tr v-for="r in items" :key="r.id"><td><input v-model="selected" :value="r.id" type="checkbox" :disabled="busy || r.status !== 'PENDING'" :aria-label="`选择支出 ${r.id}`" /></td><td>{{ r.expense_date }}</td><td><RouterLink :to="`/admin/expenses/${r.id}`" class="link">{{ r.title }}</RouterLink></td><td>{{ r.category_label }}</td><td>{{ r.payer }}</td><td>{{ r.currency }} {{ r.amount }}</td><td>¥ {{ r.rmb_amount }}</td><td>{{ statusLabels[r.status] }}</td><td><div class="flex gap-3"><RouterLink :to="`/admin/expenses/${r.id}`" class="link">详情</RouterLink><RouterLink v-if="r.active" :to="`/admin/expenses/${r.id}/edit`" class="link">编辑</RouterLink><RouterLink :to="`/admin/expenses/new?copy=${r.id}`" class="link">复制一笔</RouterLink><button v-if="r.status === 'PENDING'" class="link" @click="reimbursing = [r]">登记报销</button><button v-if="r.active && r.status !== 'REIMBURSED'" class="link" @click="voidRow(r)">作废</button></div></td></tr><tr v-if="!items.length"><td colspan="9" class="text-center">{{ busy ? '正在读取…' : '没有符合条件的记录' }}</td></tr></tbody>
    </table></div>
    <div class="flex flex-wrap items-center gap-3"><span>共 {{ total }} 条，第 {{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }} 页</span><button class="btn-secondary" :disabled="page <= 1 || busy" @click="page--">上一页</button><button class="btn-secondary" :disabled="page * 20 >= total || busy" @click="page++">下一页</button></div>
  </div>
</template>
