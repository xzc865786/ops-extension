<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { ACCOUNT_STATUSES, accountStatusLabels, accountsPath, errorText, type AccountMeta, type AccountStatus, type SecretField } from '@/api/accounts'
const route = useRoute(), router = useRouter()
const isEdit = computed(() => !!route.params.id)
const meta = ref<AccountMeta>({ clients: [], owners: [], plans: [], vault_ready: true })
const form = reactive({ client: '', login: '', status: 'STANDBY' as AccountStatus, plan: '', expires_on: '', owner: '', phone: '', recovery_email: '', notes: '' })
// On edit a secret is only sent when the admin chose to change or clear it; omitted means unchanged.
const secrets = reactive<Record<SecretField, { value: string; mode: 'keep' | 'set' | 'clear'; present: boolean; visible: boolean }>>({
  password: { value: '', mode: 'set', present: false, visible: false },
  secret_notes: { value: '', mode: 'set', present: false, visible: false },
})
const version = ref(1), busy = ref(false), loading = ref(true), error = ref('')
onMounted(async () => {
  try {
    meta.value = (await api.get(accountsPath + '/meta')).data
    if (isEdit.value) {
      const { data } = await api.get(`${accountsPath}/${route.params.id}`)
      if (data.archived) throw new Error('已归档的账号请先恢复再编辑')
      for (const k of Object.keys(form)) (form as any)[k] = data[k] ?? ''
      version.value = data.version
      secrets.password.present = data.has_password; secrets.secret_notes.present = data.has_secret_notes
      for (const s of Object.values(secrets)) s.mode = s.present ? 'keep' : 'set'
    }
  } catch (e) { error.value = errorText(e) } finally { loading.value = false }
})
const needsVault = computed(() => Object.values(secrets).some(s => s.mode === 'set' && s.value))
async function submit() {
  if (busy.value) return
  error.value = ''
  const body: Record<string, unknown> = { ...form, expires_on: form.expires_on || null }
  for (const [field, s] of Object.entries(secrets)) {
    // An empty "set" leaves the stored value alone; clearing is always an explicit choice.
    if (s.mode === 'set' && s.value) body[field] = s.value
    else if (s.mode === 'clear') body[field] = null
  }
  if (isEdit.value) body.version = version.value
  busy.value = true
  try {
    const { data } = isEdit.value ? await api.patch(`${accountsPath}/${route.params.id}`, body) : await api.post(accountsPath, body)
    await router.push(`/admin/accounts/${data.id}`)
  } catch (e) { error.value = errorText(e) } finally { busy.value = false }
}
</script>
<template>
  <form class="card card-body max-w-3xl space-y-5" autocomplete="off" @submit.prevent="submit">
    <RouterLink to="/admin/accounts" class="link">← 返回账号记录</RouterLink><h1 class="page-title">{{ isEdit ? '编辑账号' : '新增账号' }}</h1>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p><p v-if="loading" class="muted">正在读取…</p>
    <p v-if="!loading && !meta.vault_ready" class="alert-warning">服务器未配置账号加密密钥，暂不能保存密码和敏感备注；其余信息可以保存。</p>
    <fieldset :disabled="busy || loading" class="space-y-4">
      <div class="grid sm:grid-cols-2 gap-4">
        <div><label for="account-client" class="input-label">客户端</label><input id="account-client" v-model="form.client" list="account-clients" class="input" required maxlength="50" placeholder="例如 Claude、ChatGPT、Google" /><datalist id="account-clients"><option v-for="c in meta.clients" :key="c">{{ c }}</option></datalist></div>
        <div><label for="account-login" class="input-label">登录账号</label><input id="account-login" v-model="form.login" class="input" required maxlength="255" placeholder="通常是邮箱" autocomplete="off" /></div>
      </div>
      <div>
        <span class="input-label">状态</span>
        <div class="tabs w-fit" role="radiogroup" aria-label="状态"><button v-for="s in ACCOUNT_STATUSES" :key="s" type="button" role="radio" class="tab" :class="{ 'tab-active': form.status === s }" :aria-checked="form.status === s" @click="form.status = s">{{ accountStatusLabels[s] }}</button></div>
      </div>
      <div v-for="field in (['password', 'secret_notes'] as const)" :key="field" class="space-y-2">
        <label :for="`account-${field}`" class="input-label">{{ field === 'password' ? '密码（加密保存）' : '敏感备注（加密保存，选填：恢复码、密保问题等）' }}</label>
        <div v-if="secrets[field].present && secrets[field].mode !== 'set'" class="flex flex-wrap items-center gap-3 text-sm">
          <span :class="secrets[field].mode === 'clear' ? 'badge-danger' : 'badge-success'">{{ secrets[field].mode === 'clear' ? '保存后将清除' : '已设置，保持不变' }}</span>
          <button type="button" class="link" @click="secrets[field].mode = 'set'">修改</button>
          <button v-if="secrets[field].mode === 'keep'" type="button" class="link" @click="secrets[field].mode = 'clear'">清除</button>
          <button v-else type="button" class="link" @click="secrets[field].mode = 'keep'">撤销清除</button>
        </div>
        <template v-else>
          <div v-if="field === 'password'" class="flex gap-2">
            <input :id="`account-${field}`" v-model="secrets[field].value" :type="secrets[field].visible ? 'text' : 'password'" class="input" maxlength="1000" autocomplete="new-password" :placeholder="isEdit && secrets[field].present ? '输入新密码' : '选填'" />
            <button type="button" class="btn-secondary shrink-0" @click="secrets[field].visible = !secrets[field].visible">{{ secrets[field].visible ? '隐藏' : '显示' }}</button>
          </div>
          <textarea v-else :id="`account-${field}`" v-model="secrets[field].value" class="input" rows="3" maxlength="10000" autocomplete="off" />
          <button v-if="secrets[field].present" type="button" class="link text-sm" @click="secrets[field].mode = 'keep'; secrets[field].value = ''">不修改</button>
        </template>
      </div>
      <div class="grid sm:grid-cols-3 gap-4">
        <div><label for="account-plan" class="input-label">套餐（选填）</label><input id="account-plan" v-model="form.plan" list="account-plans" class="input" maxlength="50" placeholder="Plus、Pro、Max…" /><datalist id="account-plans"><option v-for="p in meta.plans" :key="p">{{ p }}</option></datalist></div>
        <div><label for="account-expires" class="input-label">到期日（选填）</label><input id="account-expires" v-model="form.expires_on" type="date" class="input" /></div>
        <div><label for="account-owner" class="input-label">使用人（选填）</label><input id="account-owner" v-model="form.owner" list="account-owners" class="input" maxlength="100" /><datalist id="account-owners"><option v-for="o in meta.owners" :key="o">{{ o }}</option></datalist></div>
        <div><label for="account-phone" class="input-label">绑定手机（选填）</label><input id="account-phone" v-model="form.phone" class="input" maxlength="50" autocomplete="off" /></div>
        <div class="sm:col-span-2"><label for="account-recovery" class="input-label">辅助邮箱（选填）</label><input id="account-recovery" v-model="form.recovery_email" class="input" maxlength="255" autocomplete="off" /></div>
      </div>
      <div><label for="account-notes" class="input-label">备注（选填，不加密，请勿填写密码）</label><textarea id="account-notes" v-model="form.notes" class="input" rows="3" maxlength="10000" /></div>
    </fieldset>
    <div class="flex flex-wrap gap-3"><button class="btn-primary" :disabled="busy || loading || (needsVault && !meta.vault_ready)">{{ busy ? '正在保存…' : '保存' }}</button><RouterLink :to="isEdit ? `/admin/accounts/${route.params.id}` : '/admin/accounts'" class="btn-ghost">取消</RouterLink></div>
  </form>
</template>
