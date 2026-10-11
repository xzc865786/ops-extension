<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { ledgerPath, errorText } from '@/api/ledger'
import { downloadAttachment } from '@/utils/attachments'
const route = useRoute(), inventory = ref<any>({ items: [], unconfirmed_count: 0 }), original = ref<any>(null), events = ref<any[]>([]), error = ref(''), pendingOnly = ref(true)
const shown = computed(() => inventory.value.items.filter((r: any) => !pendingOnly.value || !r.record_id))
const states: Record<string,string> = { DRAFT:'草稿', SUBMITTED:'已提交', APPROVED:'已审批', REJECTED:'已驳回', PAID:'已付款（不代表已报销）', CANCELLED:'已取消' }
async function open(id: number) {
  try { const [detail, history] = await Promise.all([api.get('/admin/expenses/' + id), api.get(`/admin/expenses/${id}/events`)]); original.value = detail.data; events.value = history.data }
  catch (e) { error.value = errorText(e) }
}
onMounted(async () => { try { inventory.value = (await api.get(ledgerPath + '/history')).data; if (route.query.claim) await open(Number(route.query.claim)) } catch (e) { error.value = errorText(e) } })
async function download(a: any) { try { await downloadAttachment(a.id, a.file_name, 'expense') } catch (e) { error.value = errorText(e) } }
</script>
<template>
  <div class="space-y-5">
    <RouterLink to="/admin/expenses" class="link">← 返回支出记录</RouterLink><h1 class="page-title">历史单据（只读）</h1>
    <p class="alert-warning">历史未核对记录未计入：{{ inventory.unconfirmed_count }} 笔。申请人不一定是付款人，旧“已付款”不能直接认定为报销。异常资料继续完整保留。</p>
    <p v-if="error" class="alert-error">{{ error }}</p><label class="flex gap-2"><input v-model="pendingOnly" type="checkbox" />仅显示待核对</label>
    <RouterLink class="link" to="/admin/suppliers">历史主数据资料</RouterLink>
    <div class="table-wrap"><table class="table"><thead><tr><th>原单编号</th><th>日期</th><th>历史状态</th><th>原币金额</th><th>付款异常</th><th>附件数</th><th>操作</th></tr></thead><tbody><tr v-for="r in shown" :key="r.id"><td>{{ r.claim_no }}</td><td>{{ r.expense_date }}</td><td>{{ states[r.status] || r.status }}</td><td>{{ r.currency }} {{ r.amount }}</td><td>{{ r.anomalies.join('、') || '待人工核对付款人和报销情况' }}</td><td>{{ r.attachment_count }}</td><td><button class="link" @click="open(r.id)">查看原单</button> <RouterLink v-if="r.record_id" class="link" :to="`/admin/expenses/${r.record_id}`">已迁入 #{{ r.record_id }}</RouterLink></td></tr></tbody></table></div>
    <div v-if="original" class="card card-body space-y-4">
      <h2 class="section-title">原单 {{ original.claim_no }} · {{ states[original.status] || original.status }}</h2>
      <p>{{ original.expense_date }} · {{ original.currency }} {{ original.amount_tax_included }} · {{ original.description || '无说明' }}</p>
      <p class="muted">申请人编号 #{{ original.applicant_user_id }}，此信息不用于推断付款人。原单、税务、付款流水和事件不会被迁入流程修改。</p>
      <div class="table-wrap"><table class="table"><thead><tr><th>原单明细</th><th>数量</th><th>单价</th><th>金额</th></tr></thead><tbody><tr v-for="i in original.items" :key="i.id"><td>{{ i.description }}</td><td>{{ i.quantity }}</td><td>{{ i.unit_price }}</td><td>{{ i.amount }}</td></tr></tbody></table></div>
      <h3 class="section-title">历史付款流水</h3><div v-for="p in original.payments" :key="p.id">#{{ p.id }} · {{ p.currency }} {{ p.amount }} · {{ p.paid_at }} · {{ p.notes }}</div>
      <h3 class="section-title">原附件</h3><div v-for="a in original.attachments" :key="a.id"><button class="link" @click="download(a)">{{ a.file_name }}</button></div>
      <details><summary>查看原始税务、付款及其他完整资料</summary><pre class="text-xs whitespace-pre-wrap break-all">{{ JSON.stringify(original, null, 2) }}</pre></details><details><summary>查看历史操作事件</summary><pre class="text-xs whitespace-pre-wrap break-all">{{ JSON.stringify(events, null, 2) }}</pre></details>
      <RouterLink v-if="!inventory.items.find((r: any) => r.id === original.id)?.record_id" class="btn-primary" :to="`/admin/expenses/new?history=${original.id}`">人工确认后迁入</RouterLink>
    </div>
  </div>
</template>
