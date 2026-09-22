<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const toast = useToast()
const claim = ref<any>(null)
const accounts = ref<any[]>([])
const rejectReason = ref('')
const busy = ref(false)
const payment = reactive<any>({ amount: 0, payment_account_id: null, paid_at: '', reference_no: '', notes: '' })
const invoice = reactive<any>({})
const attachmentType = ref('INVOICE')
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const attachmentTypes = [
  { value: 'INVOICE', label: '发票' }, { value: 'RECEIPT', label: '收据' },
  { value: 'CONTRACT', label: '合同' }, { value: 'PAYMENT_SCREENSHOT', label: '付款截图' },
  { value: 'BANK_SLIP', label: '银行回单' }, { value: 'OTHER', label: '其他' },
]
const invoiceFields = ['invoice_status', 'invoice_type', 'invoice_number', 'invoice_date',
  'seller_name', 'seller_tax_no', 'buyer_name', 'buyer_tax_no',
  'amount_tax_excluded', 'tax_rate', 'tax_amount', 'deductible']

function message(e: any, fallback: string) {
  return e.response?.data?.detail?.detail || e.response?.data?.detail || fallback
}

async function load() {
  const { data } = await api.get(`/admin/expenses/${route.params.id}`)
  claim.value = data
  payment.amount = Number(data.remaining_amount)
  payment.payment_account_id = data.payment_account_id
  for (const key of invoiceFields) invoice[key] = data[key] ?? (key === 'invoice_status' ? 'NONE' : null)
}

onMounted(async () => {
  try {
    const [, accountResponse] = await Promise.all([load(), api.get('/admin/payment-accounts')])
    accounts.value = accountResponse.data
  } catch (e: any) { toast.error(message(e, '报账详情加载失败')) }
})

async function act(path: string, body?: any) {
  try {
    await api.post(`/admin/expenses/${route.params.id}/${path}`, body)
    await load()
    toast.success('操作成功')
  } catch (e: any) { toast.error(message(e, '操作失败')) }
}

async function addPayment() {
  if (busy.value) return
  busy.value = true
  try {
    const body = {
      ...payment,
      payment_account_id: payment.payment_account_id || null,
      paid_at: payment.paid_at ? new Date(payment.paid_at).toISOString() : null,
    }
    await api.post(`/admin/expenses/${route.params.id}/payments`, body)
    await load()
    payment.reference_no = ''
    payment.notes = ''
    payment.paid_at = ''
    toast.success('付款已登记')
  } catch (e: any) { toast.error(message(e, '付款登记失败')) }
  finally { busy.value = false }
}

async function saveInvoice() {
  try {
    const body: any = {}
    for (const key of invoiceFields) body[key] = invoice[key] === '' ? null : invoice[key]
    await api.put(`/admin/expenses/${route.params.id}/invoice`, body)
    await load()
    toast.success('发票信息已保存')
  } catch (e: any) { toast.error(message(e, '发票保存失败')) }
}

function chooseFile(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] || null
}

async function uploadAttachment() {
  if (!selectedFile.value || busy.value) return
  busy.value = true
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    await api.post(`/admin/expenses/${route.params.id}/attachments`, form, {
      params: { attachment_type: attachmentType.value },
    })
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await load()
    toast.success('附件已上传')
  } catch (e: any) { toast.error(message(e, '附件上传失败')) }
  finally { busy.value = false }
}
</script>

<template>
  <div v-if="claim" class="space-y-4">
    <div class="card p-4">
      <div class="flex justify-between gap-3">
        <h1 class="page-title">{{ claim.claim_no }}</h1>
        <RouterLink v-if="['DRAFT', 'REJECTED'].includes(claim.status)"
          :to="`/admin/expenses/${claim.id}/edit`" class="btn-secondary">编辑</RouterLink>
      </div>
      <p class="text-sm muted">{{ claim.status }} · {{ claim.category }} · {{ claim.pay_type }} ·
        {{ claim.currency }} {{ claim.amount_tax_included }}</p>
      <p class="text-sm mt-2">{{ claim.description }}</p>
      <ul class="text-sm mt-2 list-disc pl-5">
        <li v-for="it in claim.items" :key="it.id">{{ it.description }} × {{ it.quantity }} = {{ it.amount }}</li>
      </ul>
      <div class="flex flex-wrap gap-2 mt-3 text-sm">
        <button v-if="['DRAFT','REJECTED'].includes(claim.status)" class="btn-secondary btn-sm" @click="act('submit')">提交</button>
        <button v-if="claim.status==='SUBMITTED'" class="btn-secondary btn-sm" @click="act('approve')">审批通过</button>
        <button v-if="claim.status==='SUBMITTED'" class="btn-secondary btn-sm" @click="act('reject', { reason: rejectReason || '驳回' })">驳回</button>
        <button v-if="['DRAFT','SUBMITTED'].includes(claim.status)" class="btn-secondary btn-sm" @click="act('cancel')">取消</button>
      </div>
      <input v-if="claim.status==='SUBMITTED'" v-model="rejectReason" class="input mt-2" placeholder="驳回原因" />
    </div>

    <div class="card p-4 text-sm space-y-3">
      <h2 class="font-medium">付款</h2>
      <p>累计已付 {{ claim.currency }} {{ claim.paid_total }} · 剩余应付 {{ claim.currency }} {{ claim.remaining_amount }}</p>
      <p v-if="claim.payment_reconciliation_required" class="text-amber-300">历史付款记录存在异常，须先核对后用于财务验收。</p>
      <div v-if="claim.status==='APPROVED'" class="grid grid-cols-1 md:grid-cols-3 gap-2">
        <input v-model.number="payment.amount" type="number" min="0.01" step="0.01" class="input" aria-label="付款金额" />
        <input v-model="payment.paid_at" type="datetime-local" class="input" aria-label="付款时间" />
        <select v-model="payment.payment_account_id" class="input" aria-label="付款账户">
          <option :value="null">未指定账户</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <input v-model="payment.reference_no" class="input" placeholder="交易号" />
        <input v-model="payment.notes" class="input" placeholder="备注" />
        <button class="btn-primary" :disabled="busy" @click="addPayment">登记付款</button>
      </div>
      <div v-if="claim.payments?.length" class="table-wrap"><table class="table">
        <thead><tr><th>时间</th><th>金额</th><th>账户</th><th>交易号</th><th>备注</th></tr></thead>
        <tbody><tr v-for="p in claim.payments" :key="p.id">
          <td>{{ p.paid_at }}</td><td>{{ p.currency }} {{ p.amount }}</td>
          <td>{{ accounts.find(a => a.id === p.payment_account_id)?.name || '未指定' }}</td>
          <td>{{ p.reference_no || '—' }}</td><td>{{ p.notes || '—' }}</td>
        </tr></tbody>
      </table></div>
    </div>

    <div class="card p-4 text-sm space-y-3">
      <h2 class="font-medium">发票信息</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label>状态<select v-model="invoice.invoice_status" class="input">
          <option>NONE</option><option>PENDING</option><option>RECEIVED</option><option>NOT_REQUIRED</option>
        </select></label>
        <label>类型<select v-model="invoice.invoice_type" class="input">
          <option :value="null">未指定</option><option>VAT_SPECIAL</option><option>VAT_NORMAL</option>
          <option>RECEIPT</option><option>OTHER</option>
        </select></label>
        <label>发票号<input v-model="invoice.invoice_number" class="input" /></label>
        <label>发票日期<input v-model="invoice.invoice_date" type="date" class="input" /></label>
        <label>销方名称<input v-model="invoice.seller_name" class="input" /></label>
        <label>销方税号<input v-model="invoice.seller_tax_no" class="input" /></label>
        <label>购方名称<input v-model="invoice.buyer_name" class="input" /></label>
        <label>购方税号<input v-model="invoice.buyer_tax_no" class="input" /></label>
        <label>未税金额<input v-model.number="invoice.amount_tax_excluded" type="number" step="0.01" class="input" /></label>
        <label>税率<input v-model.number="invoice.tax_rate" type="number" step="0.0001" class="input" /></label>
        <label>税额<input v-model.number="invoice.tax_amount" type="number" step="0.01" class="input" /></label>
      </div>
      <label class="flex items-center gap-2"><input v-model="invoice.deductible" type="checkbox" />预计可抵扣</label>
      <button class="btn-secondary" @click="saveInvoice">保存发票信息</button>
    </div>

    <div class="card p-4 text-sm space-y-3">
      <h2 class="font-medium">附件</h2>
      <p class="muted">单个文件不超过 20 MB；支持图片、PDF、.log、.txt。</p>
      <div class="flex flex-wrap gap-2">
        <select v-model="attachmentType" class="input">
          <option v-for="type in attachmentTypes" :key="type.value" :value="type.value">{{ type.label }}</option>
        </select>
        <input ref="fileInput" type="file" accept="image/*,.pdf,.log,.txt" @change="chooseFile" />
        <button class="btn-secondary" :disabled="busy || !selectedFile" @click="uploadAttachment">上传</button>
      </div>
      <ul v-if="claim.attachments?.length" class="space-y-1">
        <li v-for="a in claim.attachments" :key="a.id">
          {{ attachmentTypes.find(type => type.value === a.attachment_type)?.label || a.attachment_type }} ·
          <a class="link" :href="`/ext/api/v1/attachments/${a.id}/download?source=expense`" target="_blank" rel="noopener">{{ a.file_name }}</a>
          · {{ a.file_size }} bytes
        </li>
      </ul>
      <p v-else class="muted">暂无附件</p>
    </div>
  </div>
</template>
