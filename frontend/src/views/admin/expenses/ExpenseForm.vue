<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, useTemplateRef, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { emptyMeta, ledgerPath, errorText, uploadProof } from '@/api/ledger'
import { beijingToday, cents, conversionController, type ConversionState } from '@/utils/expenseMoney'
import { formatDateTime } from '@/utils/display'
import { useToast } from '@/composables/useToast'
const route = useRoute(), router = useRouter(), toast = useToast()
const isEdit = computed(() => !!route.params.id)
const meta = ref(emptyMeta())
const form = reactive({ title: '', expense_date: beijingToday(), category: 'CLOUD_SERVER', payer: '', merchant: '', needs_reimbursement: true, notes: '' })
const conversion = reactive<ConversionState>({ currency: 'CNY', amount: '', rmb_amount: '', amount_mode: 'AUTO', quote: null, pendingDecision: false, loading: false, error: '' })
const controller = conversionController(conversion, async refresh => (await api.get(ledgerPath + '/rate', { params: { refresh } })).data)
const version = ref(1), busy = ref(false), loading = ref(true), error = ref(''), file = ref<File | null>(null)
const createdId = ref<number | null>(null), uploadFailed = ref(false)
let key = crypto.randomUUID()
const ambiguousRetry = ref(false)
const coreLocked = ref(false)
const moreOpen = ref(false), saveAndNext = ref(false), categoryTouched = ref(false)
const titleInput = useTemplateRef<HTMLInputElement>('titleInput'), proofInput = useTemplateRef<HTMLInputElement>('proofInput')
let submittedBody: any = null
// A known merchant suggests the category it was last filed under, until the category is picked by hand.
watch(() => form.merchant, merchant => {
  const category = meta.value.merchant_categories[merchant.trim()]
  if (category && !categoryTouched.value && !loading.value) form.category = category
})
const recentPayers = computed(() => meta.value.recent_payers.filter(p => p !== form.payer).slice(0, 3))
onMounted(async () => {
  try {
    meta.value = { ...emptyMeta(), ...(await api.get(ledgerPath + '/meta')).data }
    if (isEdit.value || route.query.copy) {
      const { data } = await api.get(ledgerPath + '/' + (route.params.id || route.query.copy))
      if (isEdit.value && !data.active) throw new Error('作废记录不可编辑')
      for (const k of Object.keys(form)) (form as any)[k] = data[k]
      Object.assign(conversion, { currency: data.currency, amount: data.amount, rmb_amount: data.rmb_amount, amount_mode: data.amount_mode,
        quote: data.quote_id ? { id: data.quote_id, rate: data.reference_rate, effective_date: data.rate_date, fetched_at: data.rate_fetched_at, source: data.rate_source } : null })
      version.value = data.version
      coreLocked.value = isEdit.value && data.status === 'REIMBURSED'
      moreOpen.value = !!(form.merchant || form.notes)
      categoryTouched.value = true
      if (route.query.copy) { form.payer = ''; form.expense_date = beijingToday(); form.needs_reimbursement = true; if (conversion.currency === 'USD') await controller.refresh(false) }
    }
  } catch (e) { error.value = errorText(e) } finally { loading.value = false }
})
onBeforeUnmount(controller.dispose)
// Keeps date, payer and category for consecutive entries; everything else starts over.
function resetForNext(title: string) {
  Object.assign(form, { title: '', merchant: '', notes: '', needs_reimbursement: true })
  // A USD run keeps the fetched quote, so the next amount converts without another request.
  Object.assign(conversion, { amount: '', rmb_amount: '', amount_mode: 'AUTO', pendingDecision: false, error: '' })
  file.value = null; if (proofInput.value) proofInput.value.value = ''
  key = crypto.randomUUID(); submittedBody = null; createdId.value = null; uploadFailed.value = false; ambiguousRetry.value = false
  toast.success(`已保存：${title}`)
  void nextTick(() => titleInput.value?.focus())
}
async function submit(next = false) {
  if (busy.value) return
  error.value = ''
  saveAndNext.value = next
  try {
    cents(conversion.amount); if (conversion.currency === 'USD') cents(conversion.rmb_amount)
    if (!form.title.trim() || !form.payer.trim()) throw new Error('请填写购买内容和付款人')
    if (conversion.pendingDecision) throw new Error('原币金额已改变，请先选择保留手填金额或重新换算')
    if (conversion.currency === 'USD' && conversion.amount_mode === 'AUTO' && !conversion.quote) throw new Error('请获取汇率或手填人民币金额')
    busy.value = true
    if (!uploadFailed.value) {
      const body: any = { ...form, currency: conversion.currency, amount: conversion.amount, rmb_amount: conversion.currency === 'USD' ? conversion.rmb_amount : null, amount_mode: conversion.amount_mode, quote_id: conversion.quote?.id || null }
      if (isEdit.value) body.version = version.value; else body.idempotency_key = key
      if (!isEdit.value) submittedBody ||= body
      const { data } = isEdit.value ? await api.patch(ledgerPath + '/' + route.params.id, body) : await api.post(ledgerPath, submittedBody)
      createdId.value = data.id; version.value = data.version
    }
    if (file.value) {
      try { await uploadProof(`${ledgerPath}/${createdId.value}`, file.value) }
      catch (e) { uploadFailed.value = true; throw new Error('支出已保存，凭证上传失败。点击“重试上传凭证”只会补传文件。' + errorText(e)) }
    }
    if (next && !isEdit.value) resetForNext(form.title.trim())
    else await router.push(`/admin/expenses/${createdId.value}`)
  } catch (e) {
    if ((e as any).response?.status < 500 && !uploadFailed.value) { submittedBody = null; ambiguousRetry.value = false }
    else if (!isEdit.value && !uploadFailed.value && submittedBody) ambiguousRetry.value = true
    error.value = errorText(e)
  } finally { busy.value = false }
}
const saving = computed(() => busy.value || loading.value || conversion.pendingDecision || conversion.loading)
</script>
<template>
  <form class="card card-body max-w-3xl space-y-5" @submit.prevent="submit(saveAndNext)">
    <RouterLink to="/admin/expenses" class="link">← 返回支出记录</RouterLink><h1 class="page-title">{{ isEdit ? '编辑支出' : '记一笔' }}</h1>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p><p v-if="loading" class="muted">正在读取…</p>
    <p v-if="ambiguousRetry" class="alert-warning">保存结果暂未确认。重试会使用原提交内容与同一重试编号，防止重复创建。</p>
    <p v-if="coreLocked" class="alert-warning">已报销支出的金额、付款人、日期和报销选择已锁定。更正这些信息请返回详情，先撤销所属报销批次。</p>
    <fieldset :disabled="busy || loading || uploadFailed || ambiguousRetry" class="space-y-4">
      <div><label for="expense-title" class="input-label">买了什么</label><input id="expense-title" ref="titleInput" v-model="form.title" class="input" required maxlength="200" placeholder="例如：新加坡服务器 10 月续费" /></div>
      <div class="grid sm:grid-cols-[1fr_auto] gap-4 items-end">
        <div><label for="expense-amount" class="input-label">金额{{ conversion.currency === 'USD' ? '（美元）' : '（人民币）' }}</label><input id="expense-amount" :value="conversion.amount" @input="controller.setAmount(($event.target as HTMLInputElement).value)" class="input text-lg tabular-nums" inputmode="decimal" required placeholder="0.00" :disabled="coreLocked" /></div>
        <div class="tabs h-11 items-center" role="radiogroup" aria-label="币种">
          <button v-for="c in (['CNY', 'USD'] as const)" :key="c" type="button" role="radio" class="tab !py-1.5" :class="{ 'tab-active': conversion.currency === c }" :aria-checked="conversion.currency === c" :disabled="coreLocked" @click="conversion.currency !== c && controller.setCurrency(c)">{{ c === 'CNY' ? '人民币' : '美元' }}</button>
        </div>
      </div>
      <div v-if="conversion.currency === 'USD'" class="rounded-xl bg-gray-50 dark:bg-dark-900/40 p-4 space-y-3">
        <label for="expense-rmb" class="input-label">折合人民币（可直接修改）</label><input id="expense-rmb" :value="conversion.rmb_amount" @input="controller.setRmb(($event.target as HTMLInputElement).value)" class="input tabular-nums" inputmode="decimal" required :disabled="coreLocked" />
        <p v-if="conversion.loading" class="text-sm muted">正在获取最新可用参考汇率…</p>
        <div v-if="conversion.quote" class="text-sm muted">
          按 1 美元 = {{ conversion.quote.rate }} 元换算（{{ conversion.quote.effective_date }} 汇率）<span v-if="conversion.amount_mode === 'MANUAL'" class="badge-warning ml-2">已手动调整</span>
          <details class="mt-1"><summary class="cursor-pointer w-fit">汇率来源</summary>{{ conversion.quote.source }} · 获取于 {{ formatDateTime(conversion.quote.fetched_at) }}</details>
        </div>
        <p v-else-if="conversion.amount_mode === 'MANUAL'" class="text-sm muted">人工填写，未保存外部参考汇率。<span class="badge-warning ml-2">已手动调整</span></p>
        <p v-if="conversion.error" class="alert-warning">{{ conversion.error }}</p>
        <div v-if="conversion.pendingDecision" class="alert-warning space-y-2"><p>美元原金额已修改，请确认人民币金额。</p><button type="button" class="btn-secondary" @click="controller.keepManual">保留手填人民币金额</button> <button type="button" class="btn-secondary" @click="controller.refresh(true)">重新换算</button></div>
        <button v-if="!coreLocked" type="button" class="btn-ghost btn-sm" :disabled="conversion.loading" @click="controller.refresh(true)">按最新汇率重新换算{{ conversion.amount_mode === 'MANUAL' ? '（覆盖手填结果）' : '' }}</button>
      </div>
      <div class="grid sm:grid-cols-2 gap-4">
        <div>
          <label for="expense-payer" class="input-label">付款人</label><input id="expense-payer" v-model="form.payer" list="payer-suggestions" class="input" required maxlength="100" placeholder="自由填写实际付款人" :disabled="coreLocked" /><datalist id="payer-suggestions"><option v-for="p in meta.payers" :key="p">{{ p }}</option></datalist>
          <div v-if="!coreLocked && recentPayers.length" class="mt-2 flex flex-wrap items-center gap-2 text-xs"><span class="muted">最近：</span><button v-for="p in recentPayers" :key="p" type="button" class="badge-gray hover:bg-gray-200 dark:hover:bg-dark-600" @click="form.payer = p">{{ p }}</button></div>
        </div>
        <div><label for="expense-date" class="input-label">支出日期</label><input id="expense-date" v-model="form.expense_date" type="date" class="input" required :disabled="coreLocked" /></div>
        <div><label for="expense-category" class="input-label">分类</label><select id="expense-category" v-model="form.category" class="input" @change="categoryTouched = true"><option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option></select></div>
        <label class="flex gap-2 items-center sm:mt-8"><input v-model="form.needs_reimbursement" type="checkbox" :disabled="coreLocked" />需要报销（有人垫付）</label>
      </div>
      <div><label for="expense-proof" class="input-label">付款凭证（选填，图片/PDF/日志，最多 20MB）</label><input id="expense-proof" ref="proofInput" type="file" accept="image/*,.pdf,.txt,.log" @change="file = ($event.target as HTMLInputElement).files?.[0] || null" /></div>
      <details :open="moreOpen" class="space-y-4" @toggle="moreOpen = ($event.target as HTMLDetailsElement).open">
        <summary class="cursor-pointer w-fit text-sm font-medium text-gray-700 dark:text-gray-300">更多信息（商家、备注）</summary>
        <div class="space-y-4 mt-4">
          <div><label for="expense-merchant" class="input-label">商家或平台（选填）</label><input id="expense-merchant" v-model="form.merchant" list="merchant-suggestions" class="input" maxlength="200" /><datalist id="merchant-suggestions"><option v-for="m in meta.merchants" :key="m">{{ m }}</option></datalist><p v-if="meta.merchant_categories[form.merchant.trim()] && !categoryTouched" class="mt-1 text-xs muted">已按该商家上次的分类自动选择</p></div>
          <div><label for="expense-notes" class="input-label">备注（选填）</label><textarea id="expense-notes" v-model="form.notes" class="input" rows="3" maxlength="10000" /></div>
        </div>
      </details>
    </fieldset>
    <div class="flex flex-wrap gap-3">
      <button class="btn-primary" :disabled="saving" @click="saveAndNext = false">{{ busy && !saveAndNext ? '正在保存…' : uploadFailed ? '重试上传凭证' : ambiguousRetry ? '重试原提交' : '保存支出' }}</button>
      <button v-if="!isEdit && !uploadFailed && !ambiguousRetry" type="submit" class="btn-secondary" :disabled="saving" @click="saveAndNext = true">{{ busy && saveAndNext ? '正在保存…' : '保存并再记一笔' }}</button>
      <RouterLink v-if="createdId" :to="`/admin/expenses/${createdId}`" class="btn-secondary">查看已保存记录</RouterLink>
    </div>
  </form>
</template>
