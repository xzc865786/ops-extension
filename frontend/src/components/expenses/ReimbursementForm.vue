<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import api from '@/api/client'
import { errorText, uploadProof, type ExpenseRecord } from '@/api/ledger'
import { beijingToday, totalMoney, cents } from '@/utils/expenseMoney'
const props = defineProps<{ records: ExpenseRecord[] }>()
const emit = defineEmits<{ done: []; cancel: [] }>()
const expected = computed(() => totalMoney(props.records.map(r => r.rmb_amount)))
const form = reactive({ actual_amount: expected.value, reimbursement_date: beijingToday(), notes: '', difference_reason: '' })
const differs = computed(() => { try { return cents(form.actual_amount) !== cents(expected.value) } catch { return true } })
const preview = ref<any[] | null>(null), error = ref(''), busy = ref(false), file = ref<File | null>(null), savedBatch = ref<number | null>(null)
const key = crypto.randomUUID()
let generation = 0, submittedBody: any = null
watch(form, () => { generation++; preview.value = null })
function body() { return { ...form, idempotency_key: key, records: props.records.map(r => ({ id: r.id, version: r.version })) } }
async function showPreview() {
  error.value = ''; const current = ++generation
  try { cents(form.actual_amount); busy.value = true; const { data } = await api.post('/admin/reimbursements/preview', body()); if (generation === current) preview.value = data }
  catch (e) { error.value = errorText(e) } finally { busy.value = false }
}
async function confirm() {
  if (busy.value || (!preview.value && !savedBatch.value && !submittedBody)) return
  busy.value = true; error.value = ''
  try {
    if (!savedBatch.value) { submittedBody ||= body(); const { data } = await api.post('/admin/reimbursements', submittedBody); savedBatch.value = data.id }
    if (file.value) await uploadProof('/admin/reimbursements/' + savedBatch.value, file.value)
    emit('done')
  } catch (e) {
    if ((e as any).response?.status < 500 && !savedBatch.value) submittedBody = null
    error.value = savedBatch.value ? '报销已登记，凭证上传失败。请重试上传，或关闭后到详情页补传。' : errorText(e)
  } finally { busy.value = false }
}
</script>
<template>
  <form class="card card-body space-y-4" @submit.prevent="confirm">
    <h2 class="section-title">登记报销 · {{ records[0]?.payer }}</h2><p>所选 {{ records.length }} 笔，应报销人民币 {{ expected }} 元</p>
    <p class="muted text-sm">这里只登记已完成的报销，不执行转账。金额不同仍表示整批结清，不登记部分报销。</p>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p>
    <fieldset :disabled="busy || !!savedBatch || !!submittedBody" class="grid sm:grid-cols-2 gap-4">
      <div><label for="reimbursement-actual" class="input-label">实际报销人民币金额</label><input id="reimbursement-actual" v-model="form.actual_amount" class="input" inputmode="decimal" required /></div>
      <div><label for="reimbursement-date" class="input-label">报销日期</label><input id="reimbursement-date" v-model="form.reimbursement_date" type="date" class="input" required /></div>
      <div class="sm:col-span-2"><label for="reimbursement-reason" class="input-label">差额说明（实报与应报不同时必填）</label><input id="reimbursement-reason" v-model="form.difference_reason" class="input" :required="differs" maxlength="2000" /></div>
      <div><label for="reimbursement-notes" class="input-label">备注（选填）</label><input id="reimbursement-notes" v-model="form.notes" class="input" maxlength="10000" /></div>
      <div><label for="reimbursement-proof" class="input-label">转账凭证（选填）</label><input id="reimbursement-proof" type="file" accept="image/*,.pdf,.txt,.log" @change="file = ($event.target as HTMLInputElement).files?.[0] || null" /></div>
    </fieldset>
    <div v-if="preview" class="table-wrap"><table class="table"><thead><tr><th>支出</th><th>应报销</th><th>实报分配</th><th>差额</th></tr></thead><tbody><tr v-for="p in preview" :key="p.id"><td>{{ p.title }}</td><td>{{ p.expected_amount }}</td><td>{{ p.actual_amount }}</td><td>{{ p.difference }}</td></tr></tbody></table></div>
    <div class="flex flex-wrap gap-2"><button v-if="!savedBatch && !submittedBody" type="button" class="btn-secondary" :disabled="busy" @click="showPreview">查看逐笔分配</button><button class="btn-primary" :disabled="busy || (!preview && !savedBatch && !submittedBody)">{{ busy ? '正在处理…' : savedBatch ? '重试上传凭证' : submittedBody ? '重试同一笔登记' : '确认已报销' }}</button><button type="button" class="btn-ghost" :disabled="busy" @click="savedBatch ? emit('done') : emit('cancel')">关闭</button></div>
  </form>
</template>
