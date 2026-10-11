<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { ACCOUNT_STATUSES, accountStatusLabels, accountsPath, errorText, type Account, type AccountMeta, type AccountStatus } from '@/api/accounts'
import { formatDateTime } from '@/utils/display'
import { useToast } from '@/composables/useToast'
import SecretValue from '@/components/accounts/SecretValue.vue'
const toast = useToast()
const filters = reactive({ client: '', status: '' as AccountStatus | '', keyword: '', archived: false })
const typed = ref('')
let typing: ReturnType<typeof setTimeout> | undefined
watch(typed, value => { clearTimeout(typing); typing = setTimeout(() => { filters.keyword = value }, 300) })
onBeforeUnmount(() => clearTimeout(typing))
const items = ref<Account[]>([]), clients = ref<{ client: string; count: number }[]>([]), statuses = ref<Record<string, number>>({})
const meta = ref<AccountMeta | null>(null), error = ref(''), busy = ref(false), saving = ref(0)
const total = computed(() => clients.value.reduce((sum, c) => sum + c.count, 0))
let generation = 0
async function load() {
  const current = ++generation; busy.value = true; error.value = ''
  try {
    const { data } = await api.get(accountsPath, { params: filters })
    if (current === generation) { items.value = data.items; clients.value = data.clients; statuses.value = data.statuses }
  } catch (e) { if (current === generation) error.value = errorText(e) } finally { if (current === generation) busy.value = false }
}
watch(filters, load)
onMounted(async () => {
  try { meta.value = (await api.get(accountsPath + '/meta')).data } catch (e) { error.value = errorText(e) }
  await load()
})
async function changeStatus(row: Account, event: Event) {
  const select = event.target as HTMLSelectElement, status = select.value as AccountStatus
  saving.value = row.id
  try {
    Object.assign(row, (await api.post(`${accountsPath}/${row.id}/status`, { status, version: row.version })).data)
    toast.success(`${row.login} 已改为${accountStatusLabels[status]}`)
    await load()
  } catch (e) { select.value = row.status; error.value = errorText(e) } finally { saving.value = 0 }
}
async function copyLogin(row: Account) {
  try { await navigator.clipboard.writeText(row.login); toast.success('已复制账号') } catch { toast.error('浏览器不允许复制，请手动选择账号复制') }
}
</script>
<template>
  <div class="space-y-5">
    <div class="page-toolbar !mb-0"><h1 class="page-title">账号记录</h1><div class="page-toolbar-actions"><RouterLink class="btn-primary" to="/admin/accounts/new">新增账号</RouterLink></div></div>
    <p v-if="meta && !meta.vault_ready" class="alert-warning">服务器未配置账号加密密钥（ACCOUNT_VAULT_KEY），暂不能保存或查看密码，其余信息可以正常记录。</p>
    <div class="tabs w-fit max-w-full" role="group" aria-label="按客户端查看">
      <button type="button" class="tab" :class="{ 'tab-active': !filters.client }" :aria-pressed="!filters.client" @click="filters.client = ''">全部 <span class="muted">{{ total }}</span></button>
      <button v-for="c in clients" :key="c.client" type="button" class="tab" :class="{ 'tab-active': filters.client === c.client }" :aria-pressed="filters.client === c.client" @click="filters.client = c.client">{{ c.client }} <span class="muted">{{ c.count }}</span></button>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <button type="button" class="btn-sm" :class="!filters.status ? 'btn-primary' : 'btn-secondary'" :aria-pressed="!filters.status" @click="filters.status = ''">全部状态</button>
      <button v-for="s in ACCOUNT_STATUSES" :key="s" type="button" class="btn-sm" :class="filters.status === s ? 'btn-primary' : 'btn-secondary'" :aria-pressed="filters.status === s" @click="filters.status = filters.status === s ? '' : s">{{ accountStatusLabels[s] }} {{ statuses[s] ?? 0 }}</button>
      <input v-model="typed" class="input sm:!w-64 sm:ml-auto" placeholder="搜索账号、使用人、套餐、备注" aria-label="搜索账号" />
      <label class="flex items-center gap-2 text-sm"><input v-model="filters.archived" type="checkbox" />查看已归档</label>
    </div>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p>
    <div class="table-wrap" :aria-busy="busy"><table class="table"><thead><tr><th>客户端</th><th>账号</th><th>密码</th><th>状态</th><th>套餐</th><th>到期日</th><th>使用人</th><th>更新时间</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="r in items" :key="r.id">
          <td class="font-medium">{{ r.client }}</td>
          <td><span class="inline-flex items-center gap-2"><RouterLink :to="`/admin/accounts/${r.id}`" class="link">{{ r.login }}</RouterLink><button type="button" class="link text-xs" :aria-label="`复制账号 ${r.login}`" @click="copyLogin(r)">复制</button></span></td>
          <td><SecretValue :account-id="r.id" field="password" label="密码" :present="r.has_password" /></td>
          <td><select class="input !w-auto !py-1.5 !pl-3 !pr-8" :value="r.status" :disabled="r.archived || saving === r.id" :aria-label="`${r.login} 的状态`" @change="changeStatus(r, $event)"><option v-for="s in ACCOUNT_STATUSES" :key="s" :value="s">{{ accountStatusLabels[s] }}</option></select></td>
          <td>{{ r.plan || '—' }}</td>
          <td class="tabular-nums"><span v-if="r.expires_on" :class="{ 'badge-danger': r.expiry === 'EXPIRED', 'badge-warning': r.expiry === 'SOON' }">{{ r.expires_on }}{{ r.expiry === 'EXPIRED' ? ' 已过期' : r.expiry === 'SOON' ? ' 快到期' : '' }}</span><span v-else class="muted">—</span></td>
          <td>{{ r.owner || '—' }}</td>
          <td class="muted text-xs tabular-nums">{{ formatDateTime(r.updated_at) }}</td>
          <td><div class="flex gap-3"><RouterLink :to="`/admin/accounts/${r.id}`" class="link">详情</RouterLink><RouterLink v-if="!r.archived" :to="`/admin/accounts/${r.id}/edit`" class="link">编辑</RouterLink></div></td>
        </tr>
        <tr v-if="!items.length"><td colspan="9" class="text-center muted">{{ busy ? '正在读取…' : filters.archived ? '没有已归档的账号' : '没有符合条件的账号' }}</td></tr>
      </tbody>
    </table></div>
  </div>
</template>
