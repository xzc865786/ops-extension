<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { ledgerPath, errorText, statusLabels, uploadProof } from '@/api/ledger'
import { downloadAttachment } from '@/utils/attachments'
import { formatDateTime } from '@/utils/display'
import { yuan } from '@/utils/expenseMoney'
import ReimbursementForm from '@/components/expenses/ReimbursementForm.vue'
import ReasonDialog from '@/components/ReasonDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
const route = useRoute(), record = ref<any>(null), error = ref(''), busy = ref(false), reimbursing = ref(false)
// Pending reason prompt: voiding this record, or revoking one of its batches.
const asking = ref<{ kind: 'void' } | { kind: 'revoke'; batch: any } | null>(null), dialogError = ref('')
const eventLabels: Record<string,string> = { CREATED:'创建支出', HISTORY_CONFIRMED:'确认历史单据', UPDATED:'编辑支出', VOIDED:'作废支出', REIMBURSED:'登记报销', REIMBURSEMENT_REVOKED:'撤销报销', ATTACHMENT_ADDED:'上传凭证' }
const timeFields = new Set(['rate_fetched_at'])
function auditRows(value: Record<string, unknown> | null) {
  const labels: Record<string,string> = { id:'记录编号', title:'购买内容', expense_date:'支出日期', category:'分类', payer:'付款人', merchant:'商家', currency:'币种', amount:'原币金额', rmb_amount:'人民币记账额', amount_mode:'金额模式', reference_rate:'参考汇率（1美元兑人民币）', rate_date:'汇率有效日期', rate_fetched_at:'汇率获取时间', rate_source:'汇率来源', needs_reimbursement:'需要报销', active:'有效记录', notes:'备注', legacy_claim_id:'历史原单编号', status:'报销状态', actual_amount:'实际报销分配额', difference:'差额', reason:'原因', file_name:'凭证文件名' }
  return Object.entries(value || {}).filter(([key]) => labels[key]).map(([key, value]) => {
    let display = value == null ? '—' : typeof value === 'boolean' ? (value ? '是' : '否') : String(value)
    if (key === 'status') display = statusLabels[display] || display
    if (key === 'amount_mode') display = value === 'MANUAL' ? '已手动调整' : '自动'
    if (key === 'category') display = record.value?.category === value ? record.value.category_label : display
    if (timeFields.has(key) && value) display = formatDateTime(String(value))
    return { key, label: labels[key], display }
  })
}
async function load() { try { record.value = (await api.get(`${ledgerPath}/${route.params.id}`)).data } catch (e) { error.value = errorText(e) } }
onMounted(load)
function revokeDescription(batch: any) {
  return `将撤销整个批次 #${batch.id}，影响支出 ${batch.items.map((i: any) => '#' + i.record_id).join('、')}，这些记录恢复为待报销。\n仅更正登记，不退回资金。`
}
async function confirmReason(reason: string) {
  if (!asking.value || busy.value) return
  busy.value = true; dialogError.value = ''
  try {
    if (asking.value.kind === 'void') await api.post(`${ledgerPath}/${record.value.id}/void`, { version: record.value.version, reason })
    else await api.post(`/admin/reimbursements/${asking.value.batch.id}/revoke`, { version: asking.value.batch.version, reason })
    asking.value = null; await load()
  } catch (e) { dialogError.value = errorText(e) } finally { busy.value = false }
}
async function download(a: any) { try { await downloadAttachment(a.id, a.file_name, a.source) } catch (e) { error.value = errorText(e) } }
async function upload(event: Event, batchId?: number) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || busy.value) return
  try { busy.value = true; await uploadProof(batchId ? `/admin/reimbursements/${batchId}` : `${ledgerPath}/${record.value.id}`, file); await load() } catch (e) { error.value = errorText(e) } finally { busy.value = false }
}
async function done() { reimbursing.value = false; await load() }
</script>
<template>
  <div class="space-y-5 max-w-5xl">
    <RouterLink to="/admin/expenses" class="link">← 返回支出记录</RouterLink><p v-if="error" class="alert-error" role="alert">{{ error }}</p>
    <template v-if="record">
      <div class="card card-body space-y-4">
        <div class="flex flex-wrap items-start gap-3"><h1 class="page-title min-w-0 flex-1 break-words">{{ record.title }}</h1><StatusBadge kind="ledger" :status="record.status" /></div>
        <p class="text-3xl font-bold tabular-nums">{{ yuan(record.rmb_amount) }}<span v-if="record.currency === 'USD'" class="ml-3 text-base font-normal muted">$ {{ record.amount }}</span></p>
        <div class="flex flex-wrap gap-3"><RouterLink v-if="record.active" :to="`/admin/expenses/${record.id}/edit`" class="btn-secondary">编辑</RouterLink><RouterLink :to="`/admin/expenses/new?copy=${record.id}`" class="btn-secondary">复制一笔</RouterLink><button v-if="record.status === 'PENDING'" class="btn-primary" @click="reimbursing = true">登记报销</button><button v-if="record.active && record.status !== 'REIMBURSED'" class="btn-danger" :disabled="busy" @click="dialogError = ''; asking = { kind: 'void' }">作废</button></div>
        <p v-if="record.status === 'REIMBURSED'" class="alert-warning">已报销记录的金额、付款人、日期等更正，请先撤销整个报销批次。</p>
        <dl class="grid sm:grid-cols-2 gap-3"><div>支出日期：{{ record.expense_date }}</div><div>分类：{{ record.category_label }}</div><div>付款人：{{ record.payer }}</div><div>商家：{{ record.merchant || '—' }}</div></dl>
        <div v-if="record.currency === 'USD'" class="text-sm muted">
          <template v-if="record.reference_rate">按 1 美元 = {{ record.reference_rate }} 元换算（{{ record.rate_date }} 汇率）</template><template v-else>人工填写，无外部参考汇率</template>
          <span v-if="record.amount_mode === 'MANUAL'" class="badge-warning ml-2">已手动调整</span>
          <details v-if="record.reference_rate" class="mt-1"><summary class="cursor-pointer w-fit">汇率来源</summary>{{ record.rate_source }} · 获取于 {{ formatDateTime(record.rate_fetched_at) }}</details>
        </div>
        <p class="whitespace-pre-wrap">备注：{{ record.notes || '—' }}</p>
        <h2 class="section-title">付款凭证</h2><div v-for="a in record.attachments" :key="a.source + a.id"><button class="link" @click="download(a)">{{ a.file_name }}</button></div><label class="input-label">补传付款凭证<input type="file" :disabled="busy" accept="image/*,.pdf,.txt,.log" @change="upload($event)" /></label>
      </div>
      <ReimbursementForm v-if="reimbursing" :records="[record]" @done="done" @cancel="reimbursing = false" />
      <div v-for="b in record.reimbursements" :key="b.id" class="card card-body space-y-3"><h2 class="section-title">报销批次 #{{ b.id }} · {{ b.active ? '有效' : '已撤销' }}</h2><p>付款人 {{ b.payer }} · 报销日期 {{ b.reimbursement_date }} · 实际总额 {{ yuan(b.actual_amount) }}</p><p>差额说明：{{ b.difference_reason || '无差额' }}；备注：{{ b.notes || '—' }}</p>
        <div class="table-wrap"><table class="table"><thead><tr><th>支出编号</th><th>应报销</th><th>实报分配</th><th>差额</th></tr></thead><tbody><tr v-for="i in b.items" :key="i.id"><td><RouterLink class="link" :to="`/admin/expenses/${i.record_id}`">#{{ i.record_id }}</RouterLink></td><td>{{ i.expected_amount }}</td><td>{{ i.actual_amount }}</td><td>{{ i.difference }}</td></tr></tbody></table></div>
        <div v-for="a in b.attachments" :key="a.id"><button class="link" @click="download(a)">{{ a.file_name }}</button></div><label class="input-label">补传批次转账凭证<input type="file" :disabled="busy" accept="image/*,.pdf,.txt,.log" @change="upload($event, b.id)" /></label>
        <button v-if="b.active" class="btn-danger" :disabled="busy" @click="dialogError = ''; asking = { kind: 'revoke', batch: b }">撤销整个批次（影响 {{ b.items.length }} 笔）</button><p v-else class="muted">撤销原因：{{ b.revoke_reason }} · {{ b.revoked_by_name || `操作人 #${b.revoked_by}` }} · {{ formatDateTime(b.revoked_at) }}</p>
      </div>
      <div class="card card-body space-y-3"><h2 class="section-title">操作历史</h2><details v-for="e in record.events" :key="e.id"><summary>{{ eventLabels[e.event_type] || e.event_type }} · {{ e.actor_name || `操作人 #${e.actor_user_id}` }} · {{ formatDateTime(e.created_at) }}</summary><div class="grid sm:grid-cols-2 gap-3 mt-2 text-sm"><div v-for="(value, side) in [e.old_value, e.new_value]" :key="side"><h3 class="font-medium mb-2">{{ side === 0 ? '更正前' : '更正后' }}</h3><p v-if="!auditRows(value).length" class="muted">无</p><dl v-else><div v-for="field in auditRows(value)" :key="field.key" class="mb-1"><dt class="muted">{{ field.label }}</dt><dd class="whitespace-pre-wrap break-words">{{ field.display }}</dd></div></dl></div></div></details></div>
    </template>
    <ReasonDialog v-if="asking?.kind === 'void'" title="作废这笔支出" description="作废后不再计入支出统计，原记录与凭证会保留。" confirm-text="确认作废" :busy="busy" :error="dialogError" @confirm="confirmReason" @cancel="asking = null" />
    <ReasonDialog v-else-if="asking?.kind === 'revoke'" title="撤销报销批次" :description="revokeDescription(asking.batch)" confirm-text="确认撤销" :busy="busy" :error="dialogError" @confirm="confirmReason" @cancel="asking = null" />
  </div>
</template>
