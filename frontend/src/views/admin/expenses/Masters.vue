<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const tab = ref<'suppliers' | 'centers' | 'accounts'>('suppliers')
const suppliers = ref<any[]>([])
const centers = ref<any[]>([])
const accounts = ref<any[]>([])
const sForm = reactive({ name: '', supplier_type: '' })
const cForm = reactive({ code: '', name: '' })
const aForm = reactive({ name: '', account_type: 'COMPANY_BANK', account_no_masked: '', owner_label: '' })
const error = ref('')

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

function errMsg(e: any, fallback: string) {
  return e.response?.data?.detail?.detail || e.response?.data?.detail || fallback
}

async function addSupplier() {
  error.value = ''
  try {
    await api.post('/admin/suppliers', sForm)
    sForm.name = ''
    sForm.supplier_type = ''
    await load()
    toast.success('供应商已新增')
  } catch (e: any) {
    error.value = errMsg(e, '新增供应商失败')
    toast.error(error.value)
  }
}
async function addCenter() {
  error.value = ''
  try {
    await api.post('/admin/cost-centers', cForm)
    cForm.code = ''
    cForm.name = ''
    await load()
    toast.success('成本中心已新增')
  } catch (e: any) {
    error.value = errMsg(e, '新增成本中心失败')
    toast.error(error.value)
  }
}
async function addAccount() {
  error.value = ''
  try {
    await api.post('/admin/payment-accounts', aForm)
    aForm.name = ''
    aForm.account_no_masked = ''
    await load()
    toast.success('付款账户已新增')
  } catch (e: any) {
    error.value = errMsg(e, '新增付款账户失败')
    toast.error(error.value)
  }
}
async function toggleCenter(c: any) {
  try {
    await api.patch(`/admin/cost-centers/${c.id}`, { ...c, enabled: !c.enabled })
    await load()
  } catch (e: any) {
    toast.error(errMsg(e, '更新失败'))
  }
}
</script>

<template>
  <div>
    <h1 class="page-title mb-4">主数据（供应商 / 成本中心 / 付款账户）</h1>
    <div
      v-if="error"
      class="mb-3 rounded-lg border border-red-500/40 bg-red-500/15 text-red-300 px-3 py-2 text-sm"
    >{{ error }}</div>
    <div class="flex gap-2 mb-4 text-sm">
      <button type="button" class="tab" :class="tab==='suppliers' ? 'tab-active' : ''" @click="tab='suppliers'">供应商</button>
      <button type="button" class="tab" :class="tab==='centers' ? 'tab-active' : ''" @click="tab='centers'">成本中心</button>
      <button type="button" class="tab" :class="tab==='accounts' ? 'tab-active' : ''" @click="tab='accounts'">付款账户</button>
    </div>

    <div v-if="tab==='suppliers'" class="card p-4 space-y-3">
      <div class="flex gap-2 text-sm">
        <input v-model="sForm.name" class="input" placeholder="名称" />
        <input v-model="sForm.supplier_type" class="input" placeholder="类型" />
        <button type="button" class="btn-primary px-3 py-1 rounded" @click="addSupplier">新增</button>
      </div>
      <ul v-if="suppliers.length" class="text-sm divide-y">
        <li v-for="s in suppliers" :key="s.id" class="py-2">{{ s.name }} <span class="muted">{{ s.supplier_type }}</span></li>
      </ul>
      <div v-else class="rounded-lg border border-dashed border-slate-600 bg-slate-900/40 px-3 py-4 text-sm muted">
        暂无供应商。请使用上方表单填写名称后点击「新增」创建。
      </div>
    </div>

    <div v-if="tab==='centers'" class="card p-4 space-y-3">
      <div class="flex gap-2 text-sm">
        <input v-model="cForm.code" class="input" placeholder="CODE" />
        <input v-model="cForm.name" class="input" placeholder="名称" />
        <button type="button" class="btn-primary px-3 py-1 rounded" @click="addCenter">新增</button>
      </div>
      <ul v-if="centers.length" class="text-sm divide-y">
        <li v-for="c in centers" :key="c.id" class="py-2 flex justify-between">
          <span>{{ c.code }} — {{ c.name }}</span>
          <button type="button" class="link" @click="toggleCenter(c)">{{ c.enabled ? '禁用' : '启用' }}</button>
        </li>
      </ul>
      <div v-else class="rounded-lg border border-dashed border-slate-600 bg-slate-900/40 px-3 py-4 text-sm muted">
        暂无成本中心。请使用上方表单填写 CODE 与名称后点击「新增」创建。
      </div>
    </div>

    <div v-if="tab==='accounts'" class="card p-4 space-y-3">
      <div class="flex flex-wrap gap-2 text-sm">
        <input v-model="aForm.name" class="input" placeholder="账户名" />
        <select v-model="aForm.account_type" class="input">
          <option>COMPANY_BANK</option><option>ALIPAY</option><option>WECHAT</option>
          <option>PERSONAL_BANK</option><option>OTHER</option>
        </select>
        <input v-model="aForm.account_no_masked" class="input" placeholder="脱敏账号" />
        <button type="button" class="btn-primary px-3 py-1 rounded" @click="addAccount">新增</button>
      </div>
      <ul v-if="accounts.length" class="text-sm divide-y">
        <li v-for="a in accounts" :key="a.id" class="py-2">{{ a.name }} · {{ a.account_type }} · {{ a.account_no_masked }}</li>
      </ul>
      <div v-else class="rounded-lg border border-dashed border-slate-600 bg-slate-900/40 px-3 py-4 text-sm muted">
        暂无付款账户。请使用上方表单填写账户信息后点击「新增」创建。
      </div>
    </div>
  </div>
</template>
