<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import api from '@/api/client'

const tab = ref<'suppliers' | 'centers' | 'accounts'>('suppliers')
const suppliers = ref<any[]>([])
const centers = ref<any[]>([])
const accounts = ref<any[]>([])
const sForm = reactive({ name: '', supplier_type: '' })
const cForm = reactive({ code: '', name: '' })
const aForm = reactive({ name: '', account_type: 'COMPANY_BANK', account_no_masked: '', owner_label: '' })

async function load() {
  const [s, c, a] = await Promise.all([
    api.get('/admin/suppliers'),
    api.get('/admin/cost-centers'),
    api.get('/admin/payment-accounts'),
  ])
  suppliers.value = s.data
  centers.value = c.data
  accounts.value = a.data
}
onMounted(load)

async function addSupplier() {
  await api.post('/admin/suppliers', sForm)
  sForm.name = ''
  await load()
}
async function addCenter() {
  await api.post('/admin/cost-centers', cForm)
  cForm.code = ''
  cForm.name = ''
  await load()
}
async function addAccount() {
  await api.post('/admin/payment-accounts', aForm)
  aForm.name = ''
  await load()
}
async function toggleCenter(c: any) {
  await api.patch(`/admin/cost-centers/${c.id}`, { ...c, enabled: !c.enabled })
  await load()
}
</script>

<template>
  <div>
    <h1 class="text-xl font-semibold mb-4">主数据（供应商 / 成本中心 / 付款账户）</h1>
    <div class="flex gap-2 mb-4 text-sm">
      <button class="px-3 py-1 rounded border" :class="tab==='suppliers'?'bg-sky-600 text-white':''" @click="tab='suppliers'">供应商</button>
      <button class="px-3 py-1 rounded border" :class="tab==='centers'?'bg-sky-600 text-white':''" @click="tab='centers'">成本中心</button>
      <button class="px-3 py-1 rounded border" :class="tab==='accounts'?'bg-sky-600 text-white':''" @click="tab='accounts'">付款账户</button>
    </div>

    <div v-if="tab==='suppliers'" class="bg-white rounded shadow p-4 space-y-3">
      <div class="flex gap-2 text-sm">
        <input v-model="sForm.name" class="border rounded px-2 py-1" placeholder="名称" />
        <input v-model="sForm.supplier_type" class="border rounded px-2 py-1" placeholder="类型" />
        <button class="bg-sky-600 text-white px-3 py-1 rounded" @click="addSupplier">新增</button>
      </div>
      <ul class="text-sm divide-y">
        <li v-for="s in suppliers" :key="s.id" class="py-2">{{ s.name }} <span class="text-slate-400">{{ s.supplier_type }}</span></li>
      </ul>
    </div>

    <div v-if="tab==='centers'" class="bg-white rounded shadow p-4 space-y-3">
      <div class="flex gap-2 text-sm">
        <input v-model="cForm.code" class="border rounded px-2 py-1" placeholder="CODE" />
        <input v-model="cForm.name" class="border rounded px-2 py-1" placeholder="名称" />
        <button class="bg-sky-600 text-white px-3 py-1 rounded" @click="addCenter">新增</button>
      </div>
      <ul class="text-sm divide-y">
        <li v-for="c in centers" :key="c.id" class="py-2 flex justify-between">
          <span>{{ c.code }} — {{ c.name }}</span>
          <button class="text-sky-700" @click="toggleCenter(c)">{{ c.enabled ? '禁用' : '启用' }}</button>
        </li>
      </ul>
    </div>

    <div v-if="tab==='accounts'" class="bg-white rounded shadow p-4 space-y-3">
      <div class="flex flex-wrap gap-2 text-sm">
        <input v-model="aForm.name" class="border rounded px-2 py-1" placeholder="账户名" />
        <select v-model="aForm.account_type" class="border rounded px-2 py-1">
          <option>COMPANY_BANK</option><option>ALIPAY</option><option>WECHAT</option>
          <option>PERSONAL_BANK</option><option>OTHER</option>
        </select>
        <input v-model="aForm.account_no_masked" class="border rounded px-2 py-1" placeholder="脱敏账号" />
        <button class="bg-sky-600 text-white px-3 py-1 rounded" @click="addAccount">新增</button>
      </div>
      <ul class="text-sm divide-y">
        <li v-for="a in accounts" :key="a.id" class="py-2">{{ a.name }} · {{ a.account_type }} · {{ a.account_no_masked }}</li>
      </ul>
    </div>
  </div>
</template>
