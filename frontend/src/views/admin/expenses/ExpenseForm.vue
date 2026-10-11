<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { ledgerPath, errorText, uploadProof } from '@/api/ledger'
import { beijingToday, cents, conversionController, type ConversionState } from '@/utils/expenseMoney'
const route = useRoute(), router = useRouter()
const isEdit = computed(() => !!route.params.id), historical = computed(() => !!route.query.history)
const meta = ref<any>({ categories: [], payers: [], merchants: [] })
const form = reactive({ title: '', expense_date: beijingToday(), category: 'CLOUD_SERVER', payer: '', merchant: '', needs_reimbursement: true, notes: '' })
const conversion = reactive<ConversionState>({ currency: 'CNY', amount: '', rmb_amount: '', amount_mode: 'AUTO', quote: null, pendingDecision: false, loading: false, error: '' })
const controller = conversionController(conversion, async refresh => (await api.get(ledgerPath + '/rate', { params: { refresh } })).data)
const version = ref(1), busy = ref(false), loading = ref(true), error = ref(''), file = ref<File | null>(null)
const createdId = ref<number | null>(null), uploadFailed = ref(false), key = crypto.randomUUID()
const ambiguousRetry = ref(false)
const coreLocked = ref(false)
let submittedBody: any = null
const historyDecision = ref(''), historyActual = ref(''), historyDate = ref(''), differenceReason = ref('')
onMounted(async () => {
  try {
    meta.value = (await api.get(ledgerPath + '/meta')).data
    if (isEdit.value || route.query.copy) {
      const { data } = await api.get(ledgerPath + '/' + (route.params.id || route.query.copy))
      if (isEdit.value && !data.active) throw new Error('作废记录不可编辑')
      for (const k of Object.keys(form)) (form as any)[k] = data[k]
      Object.assign(conversion, { currency: data.currency, amount: data.amount, rmb_amount: data.rmb_amount, amount_mode: data.amount_mode,
        quote: data.quote_id ? { id: data.quote_id, rate: data.reference_rate, effective_date: data.rate_date, fetched_at: data.rate_fetched_at, source: data.rate_source } : null })
      version.value = data.version
      coreLocked.value = isEdit.value && data.status === 'REIMBURSED'
      if (route.query.copy) { form.payer = ''; form.expense_date = beijingToday(); form.needs_reimbursement = true; if (conversion.currency === 'USD') await controller.refresh(false) }
    } else if (historical.value) {
      const { data } = await api.get('/admin/expenses/' + route.query.history)
      form.title = data.description || data.items?.[0]?.description || ''; form.expense_date = data.expense_date
      form.category = data.category === 'STAFF_ADVANCE' ? 'OTHER' : data.category
      if (['CNY', 'USD'].includes(data.currency)) { conversion.currency = data.currency; conversion.amount = String(data.amount_tax_included); if (data.currency === 'CNY') conversion.rmb_amount = conversion.amount }
      if (conversion.currency === 'USD') conversion.amount_mode = 'MANUAL'
    }
  } catch (e) { error.value = errorText(e) } finally { loading.value = false }
})
onBeforeUnmount(controller.dispose)
function currencyInput(event: Event) {
  const value = (event.target as HTMLSelectElement).value as 'CNY' | 'USD'
  if (historical.value) { controller.dispose(); conversion.currency = value; conversion.quote = null; conversion.rmb_amount = value === 'CNY' ? conversion.amount : ''; conversion.amount_mode = value === 'USD' ? 'MANUAL' : 'AUTO' }
  else controller.setCurrency(value)
}
async function submit() {
  if (busy.value) return
  error.value = ''
  try {
    cents(conversion.amount); if (conversion.currency === 'USD') cents(conversion.rmb_amount)
    if (!form.title.trim() || !form.payer.trim()) throw new Error('请填写购买内容和付款人')
    if (conversion.pendingDecision) throw new Error('原币金额已改变，请先选择保留手填金额或重新换算')
    if (conversion.currency === 'USD' && conversion.amount_mode === 'AUTO' && !conversion.quote) throw new Error('请获取汇率或手填人民币金额')
    if (historical.value && !historyDecision.value) throw new Error('请明确确认历史报销情况；无法确定时保留原单待核对')
    busy.value = true
    if (!uploadFailed.value) {
      const body: any = { ...form, currency: conversion.currency, amount: conversion.amount, rmb_amount: conversion.currency === 'USD' ? conversion.rmb_amount : null, amount_mode: conversion.amount_mode, quote_id: conversion.quote?.id || null }
      if (isEdit.value) body.version = version.value; else body.idempotency_key = key
      if (historical.value) { body.needs_reimbursement = historyDecision.value !== 'NOT_REQUIRED'; body.history_settled = historyDecision.value === 'REIMBURSED'; body.actual_reimbursement = body.history_settled ? historyActual.value : null; body.reimbursement_date = body.history_settled ? historyDate.value : null; body.difference_reason = differenceReason.value }
      if (!isEdit.value) submittedBody ||= body
      const { data } = isEdit.value ? await api.patch(ledgerPath + '/' + route.params.id, body) : await api.post(historical.value ? `${ledgerPath}/history/${route.query.history}/confirm` : ledgerPath, submittedBody)
      createdId.value = data.id; version.value = data.version
    }
    if (file.value) {
      try { await uploadProof(`${ledgerPath}/${createdId.value}`, file.value) }
      catch (e) { uploadFailed.value = true; throw new Error('支出已保存，凭证上传失败。点击“重试上传凭证”只会补传文件。' + errorText(e)) }
    }
    await router.push(`/admin/expenses/${createdId.value}`)
  } catch (e) {
    if ((e as any).response?.status < 500 && !uploadFailed.value) { submittedBody = null; ambiguousRetry.value = false }
    else if (!isEdit.value && !uploadFailed.value && submittedBody) ambiguousRetry.value = true
    error.value = errorText(e)
  } finally { busy.value = false }
}
</script>
<template>
  <form class="card card-body max-w-3xl space-y-5" @submit.prevent="submit">
    <RouterLink to="/admin/expenses" class="link">← 返回支出记录</RouterLink><h1 class="page-title">{{ historical ? '确认历史单据' : isEdit ? '编辑支出' : '记一笔' }}</h1>
    <p v-if="historical" class="alert-warning">请核对原单后确认付款人、人民币金额和报销情况。无法确认时返回，原资料继续保留且不计入新统计。</p>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p><p v-if="loading" class="muted">正在读取…</p>
    <p v-if="ambiguousRetry" class="alert-warning">保存结果暂未确认。重试会使用原提交内容与同一重试编号，防止重复创建。</p>
    <p v-if="coreLocked" class="alert-warning">已报销支出的金额、付款人、日期和报销选择已锁定。更正这些信息请返回详情，先撤销所属报销批次。</p>
    <fieldset :disabled="busy || loading || uploadFailed || ambiguousRetry" class="space-y-4">
      <div><label for="expense-title" class="input-label">买了什么</label><input id="expense-title" v-model="form.title" class="input" required maxlength="200" placeholder="例如：新加坡服务器 10 月续费" /></div>
      <div class="grid sm:grid-cols-2 gap-4">
        <div><label for="expense-date" class="input-label">支出日期</label><input id="expense-date" v-model="form.expense_date" type="date" class="input" required :disabled="coreLocked" /></div>
        <div><label for="expense-category" class="input-label">分类</label><select id="expense-category" v-model="form.category" class="input"><option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option></select></div>
        <div><label for="expense-payer" class="input-label">付款人</label><input id="expense-payer" v-model="form.payer" list="payer-suggestions" class="input" required maxlength="100" placeholder="自由填写实际付款人" :disabled="coreLocked" /><datalist id="payer-suggestions"><option v-for="p in meta.payers" :key="p">{{ p }}</option></datalist></div>
        <div><label for="expense-merchant" class="input-label">商家或平台（选填）</label><input id="expense-merchant" v-model="form.merchant" list="merchant-suggestions" class="input" maxlength="200" /><datalist id="merchant-suggestions"><option v-for="m in meta.merchants" :key="m">{{ m }}</option></datalist></div>
        <div><label for="expense-amount" class="input-label">原币金额</label><input id="expense-amount" :value="conversion.amount" @input="controller.setAmount(($event.target as HTMLInputElement).value)" class="input" inputmode="decimal" required :disabled="coreLocked" /></div>
        <div><label for="expense-currency" class="input-label">币种</label><select id="expense-currency" :value="conversion.currency" @change="currencyInput" class="input" :disabled="coreLocked"><option value="CNY">人民币 CNY</option><option value="USD">美元 USD</option></select></div>
      </div>
      <div v-if="conversion.currency === 'USD'" class="space-y-3">
        <label for="expense-rmb" class="input-label">折合人民币（可直接修改）</label><input id="expense-rmb" :value="conversion.rmb_amount" @input="controller.setRmb(($event.target as HTMLInputElement).value)" class="input" inputmode="decimal" required :disabled="coreLocked" />
        <p v-if="conversion.loading" class="muted">正在获取最新可用参考汇率…</p>
        <p v-if="conversion.quote" class="text-sm muted">1 美元 = {{ conversion.quote.rate }} 人民币 · {{ conversion.quote.source }} · 有效日期 {{ conversion.quote.effective_date }} · 获取时间 {{ conversion.quote.fetched_at }}</p>
        <p v-else-if="conversion.amount_mode === 'MANUAL'" class="muted">人工填写，未保存外部参考汇率。</p><p v-if="conversion.amount_mode === 'MANUAL'" class="badge-warning">已手动调整</p>
        <p v-if="conversion.error" class="alert-warning">{{ conversion.error }}</p>
        <div v-if="conversion.pendingDecision" class="alert-warning space-y-2"><p>美元原金额已修改，请确认人民币金额。</p><button type="button" class="btn-secondary" @click="controller.keepManual">保留手填人民币金额</button> <button v-if="!historical" type="button" class="btn-secondary" @click="controller.refresh(true)">重新换算</button></div>
        <button v-if="!historical && !coreLocked" type="button" class="btn-secondary" :disabled="conversion.loading" @click="controller.refresh(true)">按最新汇率重新换算{{ conversion.amount_mode === 'MANUAL' ? '（覆盖手填结果）' : '' }}</button>
      </div>
      <label v-if="!historical" class="flex gap-2 items-center"><input v-model="form.needs_reimbursement" type="checkbox" :disabled="coreLocked" />需要报销</label>
      <div v-else class="space-y-3"><label for="history-status" class="input-label">人工确认历史报销情况</label><select id="history-status" v-model="historyDecision" class="input" required><option value="">请核对后选择</option><option value="PENDING">待报销</option><option value="NOT_REQUIRED">无需报销</option><option value="REIMBURSED">已报销（有金额和日期依据）</option></select>
        <template v-if="historyDecision === 'REIMBURSED'"><label class="input-label">历史实际报销人民币金额<input v-model="historyActual" class="input" inputmode="decimal" required /></label><label class="input-label">历史报销日期<input v-model="historyDate" type="date" class="input" required /></label><label class="input-label">差额说明（金额不一致时必填）<input v-model="differenceReason" class="input" /></label></template>
      </div>
      <div><label for="expense-proof" class="input-label">付款凭证（选填，图片/PDF/日志，最多 20MB）</label><input id="expense-proof" type="file" accept="image/*,.pdf,.txt,.log" @change="file = ($event.target as HTMLInputElement).files?.[0] || null" /></div>
      <div><label for="expense-notes" class="input-label">备注（选填）</label><textarea id="expense-notes" v-model="form.notes" class="input" rows="3" maxlength="10000" /></div>
    </fieldset>
    <div class="flex flex-wrap gap-3"><button class="btn-primary" :disabled="busy || loading || conversion.pendingDecision || conversion.loading">{{ busy ? '正在保存…' : uploadFailed ? '重试上传凭证' : ambiguousRetry ? '重试原提交' : '保存支出' }}</button><RouterLink v-if="createdId" :to="`/admin/expenses/${createdId}`" class="btn-secondary">查看已保存记录</RouterLink></div>
  </form>
</template>
