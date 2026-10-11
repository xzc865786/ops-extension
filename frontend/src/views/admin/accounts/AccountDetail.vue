<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { accountFieldLabels, accountStatusLabels, accountsPath, errorText, type AccountDetail, type AccountEvent, type AccountStatus } from '@/api/accounts'
import { formatDateTime } from '@/utils/display'
import SecretValue from '@/components/accounts/SecretValue.vue'
import StatusBadge from '@/components/StatusBadge.vue'
const route = useRoute(), account = ref<AccountDetail | null>(null), error = ref(''), busy = ref(false)
const eventLabels: Record<string, string> = { CREATED: '创建账号', UPDATED: '编辑账号', STATUS_CHANGED: '修改状态', SECRET_VIEWED: '查看', SECRET_COPIED: '复制', ARCHIVED: '归档', RESTORED: '恢复' }
async function load() { try { account.value = (await api.get(`${accountsPath}/${route.params.id}`)).data } catch (e) { error.value = errorText(e) } }
onMounted(load)
async function toggleArchive() {
  if (!account.value || busy.value) return
  busy.value = true; error.value = ''
  try { account.value = (await api.post(`${accountsPath}/${account.value.id}/${account.value.archived ? 'restore' : 'archive'}`, { version: account.value.version })).data }
  catch (e) { error.value = errorText(e) } finally { busy.value = false }
}
function shown(key: string, value: unknown) {
  if (value == null || value === '') return '空'
  return key === 'status' ? accountStatusLabels[value as AccountStatus] ?? String(value) : String(value)
}
// One readable line per event; secrets appear only as "已修改"/"已清除", never their values.
function describe(e: AccountEvent): string[] {
  const d = e.detail || {}
  if (e.event_type === 'SECRET_VIEWED' || e.event_type === 'SECRET_COPIED') return [`${eventLabels[e.event_type]}了${d.field}`]
  const lines = Object.entries(d.changes || {}).map(([k, [from, to]]: [string, any]) => `${accountFieldLabels[k] || k}：${shown(k, from)} → ${shown(k, to)}`)
  for (const [label, change] of Object.entries(d.secrets || {})) lines.push(`${label}${change}`)
  return lines
}
</script>
<template>
  <div class="space-y-5 max-w-4xl">
    <RouterLink to="/admin/accounts" class="link">← 返回账号记录</RouterLink><p v-if="error" class="alert-error" role="alert">{{ error }}</p>
    <template v-if="account">
      <div class="card card-body space-y-4">
        <div class="flex flex-wrap items-center gap-3"><span class="badge-gray">{{ account.client }}</span><h1 class="page-title min-w-0 break-all">{{ account.login }}</h1><StatusBadge kind="account" :status="account.status" /><span v-if="account.archived" class="badge-gray">已归档</span></div>
        <div class="flex flex-wrap gap-3"><RouterLink v-if="!account.archived" :to="`/admin/accounts/${account.id}/edit`" class="btn-secondary">编辑</RouterLink><button type="button" :class="account.archived ? 'btn-secondary' : 'btn-ghost'" :disabled="busy" @click="toggleArchive">{{ account.archived ? '恢复' : '归档' }}</button></div>
        <dl class="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div><dt class="muted">密码</dt><dd><SecretValue :account-id="account.id" field="password" label="密码" :present="account.has_password" /></dd></div>
          <div><dt class="muted">套餐</dt><dd>{{ account.plan || '—' }}</dd></div>
          <div><dt class="muted">到期日</dt><dd><span v-if="account.expires_on" :class="{ 'badge-danger': account.expiry === 'EXPIRED', 'badge-warning': account.expiry === 'SOON' }">{{ account.expires_on }}{{ account.expiry === 'EXPIRED' ? ' 已过期' : account.expiry === 'SOON' ? ' 快到期' : '' }}</span><span v-else>—</span></dd></div>
          <div><dt class="muted">使用人</dt><dd>{{ account.owner || '—' }}</dd></div>
          <div><dt class="muted">绑定手机</dt><dd>{{ account.phone || '—' }}</dd></div>
          <div><dt class="muted">辅助邮箱</dt><dd class="break-all">{{ account.recovery_email || '—' }}</dd></div>
          <div class="sm:col-span-2"><dt class="muted">敏感备注</dt><dd><SecretValue :account-id="account.id" field="secret_notes" label="敏感备注" :present="account.has_secret_notes" multiline /></dd></div>
          <div class="sm:col-span-2"><dt class="muted">备注</dt><dd class="whitespace-pre-wrap break-words">{{ account.notes || '—' }}</dd></div>
        </dl>
      </div>
      <div class="card card-body space-y-3"><h2 class="section-title">操作历史</h2>
        <p class="text-xs muted">每次查看或复制密码、敏感备注都会记录在这里；记录中不包含密码内容。</p>
        <ul class="divide-y divide-gray-100 dark:divide-dark-700/50 text-sm">
          <li v-for="e in account.events" :key="e.id" class="py-2">
            <div class="flex flex-wrap gap-x-3"><span class="font-medium">{{ eventLabels[e.event_type] || e.event_type }}</span><span class="muted">{{ e.actor_name || `操作人 #${e.actor_user_id}` }} · {{ formatDateTime(e.created_at) }}</span></div>
            <p v-for="line in describe(e)" :key="line" class="muted break-words">{{ line }}</p>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>
