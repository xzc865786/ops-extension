<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/client'

const router = useRouter()
const meta = ref<any>({ categories: [], pay_types: [], currencies: ['CNY'] })
const centers = ref<any[]>([])
const accounts = ref<any[]>([])
const suppliers = ref<any[]>([])
const form = reactive<any>({
  expense_date: new Date().toISOString().slice(0, 10),
  category: 'CLOUD_SERVER',
  cost_center_id: null,
  supplier_id: null,
  currency: 'CNY',
  pay_type: 'COMPANY_DIRECT',
  payment_account_id: null,
  description: '',
  invoice_required: true,
  items: [{ description: '', quantity: 1, unit_price: 0 }],
})

onMounted(async () => {
  const [m, c, a, s] = await Promise.all([
    api.get('/admin/expenses/meta'),
    api.get('/admin/cost-centers'),
    api.get('/admin/payment-accounts'),
    api.get('/admin/suppliers'),
  ])
  meta.value = m.data
  centers.value = c.data.filter((x: any) => x.enabled)
  accounts.value = a.data.filter((x: any) => x.enabled)
  suppliers.value = s.data
  if (meta.value.categories?.length) form.category = meta.value.categories[0].value
})

function addItem() {
  form.items.push({ description: '', quantity: 1, unit_price: 0 })
}

async function submit() {
  const { data } = await api.post('/admin/expenses', form)
  router.push(`/admin/expenses/${data.id}`)
}
</script>

<template>
  <div class="card p-4 max-w-3xl space-y-3">
    <h1 class="page-title">新建报账</h1>
    <div class="grid grid-cols-2 gap-3 text-sm">
      <div>
        <label class="block mb-1">费用日期</label>
        <input v-model="form.expense_date" type="date" class="input" />
      </div>
      <div>
        <label class="block mb-1">分类</label>
        <select v-model="form.category" class="input">
          <option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option>
        </select>
      </div>
      <div>
        <label class="block mb-1">成本中心</label>
        <select v-model="form.cost_center_id" class="input">
          <option :value="null">未指定</option>
          <option v-for="c in centers" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>
      <div>
        <label class="block mb-1">供应商</label>
        <select v-model="form.supplier_id" class="input">
          <option :value="null">未指定</option>
          <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div>
        <label class="block mb-1">付款类型</label>
        <select v-model="form.pay_type" class="input">
          <option v-for="p in meta.pay_types" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>
      <div>
        <label class="block mb-1">付款账户</label>
        <select v-model="form.payment_account_id" class="input">
          <option :value="null">未指定</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
      </div>
      <div>
        <label class="block mb-1">币种</label>
        <select v-model="form.currency" class="input">
          <option v-for="c in meta.currencies" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
    </div>
    <div>
      <label class="block text-sm mb-1">说明</label>
      <textarea v-model="form.description" rows="2" class="input" />
    </div>
    <div>
      <div class="flex justify-between items-center mb-1">
        <h2 class="font-medium text-sm">明细</h2>
        <button type="button" class="link text-sm" @click="addItem">+ 行</button>
      </div>
      <div v-for="(it, idx) in form.items" :key="idx" class="grid grid-cols-3 gap-2 mb-2 text-sm">
        <input v-model="it.description" placeholder="描述" class="input" />
        <input v-model.number="it.quantity" type="number" step="0.01" placeholder="数量" class="input" />
        <input v-model.number="it.unit_price" type="number" step="0.01" placeholder="单价" class="input" />
      </div>
    </div>
    <button class="btn-primary px-4 py-2 rounded text-sm" @click="submit">保存草稿</button>
  </div>
</template>
