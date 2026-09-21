<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api/client'

const route = useRoute()
const claim = ref<any>(null)
const rejectReason = ref('')
const payment = reactive({ amount: 0, mark_paid: true, reference_no: '' })
const invoice = reactive({
  invoice_status: 'RECEIVED',
  invoice_type: 'VAT_SPECIAL',
  invoice_number: '',
  tax_amount: 0,
  deductible: true,
})

async function load() {
  const { data } = await api.get(`/admin/expenses/${route.params.id}`)
  claim.value = data
  payment.amount = Number(data.amount_tax_included)
}
onMounted(load)

async function act(path: string, body?: any) {
  await api.post(`/admin/expenses/${route.params.id}/${path}`, body)
  await load()
}
async function saveInvoice() {
  await api.put(`/admin/expenses/${route.params.id}/invoice`, invoice)
  await load()
}
async function addPayment() {
  await api.post(`/admin/expenses/${route.params.id}/payments`, payment)
  await load()
}
</script>

<template>
  <div v-if="claim" class="space-y-4">
    <div class="bg-white rounded shadow p-4">
      <h1 class="text-xl font-semibold">{{ claim.claim_no }}</h1>
      <p class="text-sm text-slate-500">
        {{ claim.status }} · {{ claim.category }} · {{ claim.pay_type }} · {{ claim.currency }}
        {{ claim.amount_tax_included }}
      </p>
      <p class="text-sm mt-2">{{ claim.description }}</p>
      <ul class="text-sm mt-2 list-disc pl-5">
        <li v-for="it in claim.items" :key="it.id">{{ it.description }} × {{ it.quantity }} = {{ it.amount }}</li>
      </ul>
      <div class="flex flex-wrap gap-2 mt-3 text-sm">
        <button v-if="['DRAFT','REJECTED'].includes(claim.status)" class="border px-2 py-1 rounded" @click="act('submit')">提交</button>
        <button v-if="claim.status==='SUBMITTED'" class="border px-2 py-1 rounded" @click="act('approve')">审批通过</button>
        <button v-if="claim.status==='SUBMITTED'" class="border px-2 py-1 rounded" @click="act('reject', { reason: rejectReason || '驳回' })">驳回</button>
        <button v-if="['DRAFT','SUBMITTED'].includes(claim.status)" class="border px-2 py-1 rounded" @click="act('cancel')">取消</button>
      </div>
      <input v-if="claim.status==='SUBMITTED'" v-model="rejectReason" class="border rounded px-2 py-1 text-sm mt-2" placeholder="驳回原因" />
    </div>

    <div class="bg-white rounded shadow p-4 text-sm space-y-2">
      <h2 class="font-medium">登记付款</h2>
      <div class="flex gap-2">
        <input v-model.number="payment.amount" type="number" class="border rounded px-2 py-1" />
        <input v-model="payment.reference_no" class="border rounded px-2 py-1" placeholder="流水号" />
        <button class="bg-sky-600 text-white px-3 py-1 rounded" @click="addPayment">付清并标记 PAID</button>
      </div>
    </div>

    <div class="bg-white rounded shadow p-4 text-sm space-y-2">
      <h2 class="font-medium">发票信息</h2>
      <div class="grid grid-cols-2 gap-2">
        <select v-model="invoice.invoice_status" class="border rounded px-2 py-1">
          <option>NONE</option><option>PENDING</option><option>RECEIVED</option><option>NOT_REQUIRED</option>
        </select>
        <select v-model="invoice.invoice_type" class="border rounded px-2 py-1">
          <option>VAT_SPECIAL</option><option>VAT_NORMAL</option><option>RECEIPT</option><option>OTHER</option>
        </select>
        <input v-model="invoice.invoice_number" class="border rounded px-2 py-1" placeholder="发票号" />
        <input v-model.number="invoice.tax_amount" type="number" class="border rounded px-2 py-1" placeholder="税额" />
      </div>
      <label class="flex items-center gap-2"><input v-model="invoice.deductible" type="checkbox" /> 可抵扣</label>
      <button class="border px-3 py-1 rounded" @click="saveInvoice">保存发票</button>
    </div>
  </div>
</template>
