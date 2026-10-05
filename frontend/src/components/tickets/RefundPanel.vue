<script setup lang="ts">
// Admin handling of a refund ticket: refund through Sub2API, sync the outcome, or reject.
import { computed, reactive, ref } from 'vue'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'
import ResolutionView from '@/components/tickets/ResolutionView.vue'
import { formatDateTime } from '@/utils/display'
import { OPEN_REFUND_RESULTS, REFUND_RESULT_LABELS, gatewayAmount, type OrderSnapshot } from '@/utils/ticketForm'

const props = defineProps<{ ticket: any; lookupEnabled: boolean }>()
const emit = defineEmits<{ updated: [ticket: any] }>()
const toast = useToast()

const orderRow = computed(() => props.ticket.orders?.find((o: any) => o.purpose === 'REFUND') || null)
const order = computed<OrderSnapshot | null>(() => orderRow.value?.snapshot || null)
const operations = computed<any[]>(() => props.ticket.refund_operations || [])
const openOp = computed(() => [...operations.value].reverse().find((op) => OPEN_REFUND_RESULTS.includes(op.result)) || null)
const lastOp = computed(() => operations.value[operations.value.length - 1] || null)
const closed = computed(() => props.ticket.status === 'CLOSED')
const expected = computed(() => props.ticket.form_data?.expected_amount || '')

const form = reactive({
  amount: String(expected.value || order.value?.amount || ''),
  deduct: true,
  reason: '',
})
const confirming = ref(false)
const acknowledged = ref(false)
const busy = ref(false)
const rejectReason = ref('')
const showReject = ref(false)
const manual = reactive({ amount: String(expected.value || ''), note: '' })

const amountNum = computed(() => Number(form.amount))
const amountValid = computed(() => /^\d+(\.\d{1,2})?$/.test(form.amount.trim()) && amountNum.value > 0
  && (!order.value?.amount || amountNum.value <= Number(order.value.amount)))
const back = computed(() => gatewayAmount(order.value, amountNum.value).toFixed(2))
const partial = computed(() => !!order.value?.amount && amountNum.value < Number(order.value.amount))

function errMsg(e: any, fallback: string) {
  const d = e.response?.data
  return d?.detail?.detail || (typeof d?.detail === 'string' ? d.detail : '') || fallback
}

async function run(action: () => Promise<any>, fallback: string) {
  busy.value = true
  try {
    await action()
  } catch (e: any) {
    toast.error(errMsg(e, fallback))
  } finally {
    busy.value = false
  }
}

function report(op: any) {
  if (op.result === 'SUCCESS') toast.success('退款成功，已回复用户并标记为已解决')
  else if (op.result === 'REQUIRE_FORCE') toast.push('需要确认后强制执行，请查看提示')
  else if (op.result === 'PENDING') toast.push('支付渠道正在处理退款，稍后请点“同步结果”')
  else toast.error(op.message || '退款未成功')
}

function refund(force = false) {
  return run(async () => {
    const { data } = await api.post(`/admin/tickets/${props.ticket.id}/refund`, {
      amount: form.amount.trim(), deduct_balance: form.deduct, force, reason: form.reason.trim(),
    })
    confirming.value = false
    acknowledged.value = false
    emit('updated', data.ticket)
    report(data.operation)
  }, '退款请求失败')
}

// Re-send exactly the request Sub2API asked to confirm.
function forceRefund() {
  const op = lastOp.value
  form.amount = Number(op.amount).toFixed(2)
  form.deduct = op.deduct_balance
  return refund(true)
}

function sync() {
  return run(async () => {
    const { data } = await api.post(`/admin/tickets/${props.ticket.id}/refund/sync`)
    emit('updated', data.ticket)
    const text = { REFUNDED: '订单已退款，已登记结果', PENDING: '支付渠道仍在处理退款', NOT_REFUNDED: 'Sub2API 中订单尚未退款' }[data.outcome as string]
    toast.push(data.note ? `${text}（${data.note}）` : text || '已同步')
  }, '同步失败')
}

function reject() {
  if (!rejectReason.value.trim()) {
    toast.error('请填写驳回原因')
    return
  }
  return run(async () => {
    const { data } = await api.post(`/admin/tickets/${props.ticket.id}/reject`, { reason: rejectReason.value.trim() })
    emit('updated', data)
    toast.success('已驳回并回复用户')
  }, '驳回失败')
}

function registerManual() {
  return run(async () => {
    const { data } = await api.post(`/admin/tickets/${props.ticket.id}/refund/manual`, {
      amount: manual.amount.trim(), note: manual.note.trim() || null,
    })
    emit('updated', data)
    toast.success('已登记退款并回复用户')
  }, '登记失败')
}
</script>

<template>
  <section class="card space-y-4 p-5 sm:p-6">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="section-title">退款处理</h2>
      <span v-if="expected" class="muted text-sm">· 用户期望退款 ¥{{ expected }}</span>
    </div>

    <ResolutionView v-if="ticket.resolution" :resolution="ticket.resolution" admin />

    <template v-else-if="!closed">
      <!-- 未完成的操作 -->
      <div v-if="openOp" class="alert-warning space-y-2">
        <p><strong>{{ REFUND_RESULT_LABELS[openOp.result] }}</strong>：{{ openOp.message || '退款请求已发出，等待结果' }}</p>
        <button type="button" class="btn-secondary btn-sm" :disabled="busy" @click="sync">同步结果</button>
      </div>

      <template v-else-if="lookupEnabled && orderRow">
        <div v-if="lastOp?.result === 'REQUIRE_FORCE'" class="alert-warning space-y-2">
          <p>{{ lastOp.message }}</p>
          <button type="button" class="btn-danger btn-sm" :disabled="busy" @click="forceRefund">
            强制执行退款 ¥{{ Number(lastOp.amount).toFixed(2) }}
          </button>
        </div>

        <div class="grid gap-4 sm:grid-cols-3">
          <div>
            <label class="input-label" for="refund-amount">退款额度 <span class="muted font-normal">（不超过 {{ order?.amount ?? '—' }}）</span></label>
            <input id="refund-amount" v-model="form.amount" class="input" inputmode="decimal" :disabled="confirming" />
            <p v-if="form.amount && !amountValid" class="mt-1 text-xs text-red-600">金额须大于 0、最多两位小数，且不超过订单到账额度</p>
            <p v-else-if="amountValid" class="muted mt-1 text-xs">预计原路退回 ¥{{ back }}（按实付 ¥{{ order?.pay_amount ?? '—' }} 折算）</p>
          </div>
          <div class="sm:col-span-2">
            <label class="input-label" for="refund-reason">退款原因 <span class="muted font-normal">（写入 Sub2API 订单记录）</span></label>
            <input id="refund-reason" v-model="form.reason" class="input" maxlength="100" :disabled="confirming" placeholder="例如 用户误充，额度未使用" />
          </div>
        </div>
        <label class="flex items-start gap-2 text-sm">
          <input v-model="form.deduct" type="checkbox" class="mt-0.5" :disabled="confirming" />
          <span>同时扣减用户余额 <span class="muted">（订阅订单为扣减订阅天数）</span></span>
        </label>
        <p v-if="!form.deduct" class="text-xs text-amber-700">不扣减余额：用户会同时保留退款对应的额度，请确认这是你想要的。</p>
        <ul class="list-disc space-y-0.5 pl-5 text-xs text-amber-700">
          <li v-if="partial">这是部分退款。Sub2API 中一个订单只能退款一次，部分退款后这个订单不能再退。</li>
          <li v-if="order?.order_type === 'subscription'">这是订阅订单：开启扣减会扣掉这笔订单的全部订阅天数，与退款金额无关。</li>
          <li v-if="Number(order?.bonus_amount) > 0">这笔订单有赠送额度 {{ order?.bonus_amount }}，退款不会自动扣回赠送额度。</li>
        </ul>

        <div v-if="!confirming" class="flex flex-wrap gap-2">
          <button type="button" class="btn-primary" :disabled="!amountValid || busy" @click="confirming = true">执行退款</button>
          <button type="button" class="btn-secondary" :disabled="busy" @click="sync">同步 Sub2API 结果</button>
        </div>
        <div v-else class="alert-warning space-y-2">
          <p>
            将对订单 <span class="font-mono">{{ orderRow.out_trade_no }}</span> 原路退回 <strong>¥{{ back }}</strong>（退款额度 {{ Number(form.amount).toFixed(2) }}），
            {{ form.deduct ? '并扣减用户相应余额' : '不扣减用户余额' }}。退款无法撤销。
          </p>
          <label class="flex items-center gap-2"><input v-model="acknowledged" type="checkbox" /> 我已核对订单和金额</label>
          <div class="flex gap-2">
            <button type="button" class="btn-danger btn-sm" :disabled="!acknowledged || busy" @click="refund(false)">{{ busy ? '退款中…' : '确认退款' }}</button>
            <button type="button" class="btn-secondary btn-sm" :disabled="busy" @click="confirming = false; acknowledged = false">取消</button>
          </div>
        </div>
        <p class="muted text-xs">如果已经在 Sub2API 后台直接退过款，点“同步 Sub2API 结果”即可登记。</p>
      </template>

      <p v-else-if="lookupEnabled && !orderRow" class="muted text-sm">这张工单没有关联订单（旧版工单），请在 Sub2API 后台处理后回复用户，或驳回。</p>

      <!-- 未配置订单查询：手动登记 -->
      <div v-else class="space-y-3">
        <p class="muted text-sm">未配置 Sub2API Admin API Key，不能在工单中直接退款。请在 Sub2API 后台完成退款后在这里登记。</p>
        <div class="grid gap-3 sm:grid-cols-3">
          <div>
            <label class="input-label">实际退款金额</label>
            <input v-model="manual.amount" class="input" inputmode="decimal" />
          </div>
          <div class="sm:col-span-2">
            <label class="input-label">备注</label>
            <input v-model="manual.note" class="input" maxlength="200" placeholder="例如 已在 Sub2API 订单页原路退款" />
          </div>
        </div>
        <button type="button" class="btn-primary btn-sm" :disabled="busy || !manual.amount" @click="registerManual">登记退款</button>
      </div>

      <!-- 驳回 -->
      <div v-if="!openOp" class="border-t pt-3">
        <button v-if="!showReject" type="button" class="btn-ghost btn-sm text-red-600" @click="showReject = true">驳回申请</button>
        <div v-else class="space-y-2">
          <label class="input-label" for="reject-reason">驳回原因（会回复给用户）</label>
          <textarea id="reject-reason" v-model="rejectReason" class="input" rows="2" maxlength="500" />
          <div class="flex gap-2">
            <button type="button" class="btn-danger btn-sm" :disabled="busy" @click="reject">确认驳回</button>
            <button type="button" class="btn-secondary btn-sm" @click="showReject = false">取消</button>
          </div>
        </div>
      </div>
    </template>
    <p v-else class="muted text-sm">工单已关闭。</p>

    <div v-if="operations.length" class="border-t pt-3">
      <h3 class="mb-2 text-sm font-medium">退款操作记录</h3>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>时间</th><th>额度</th><th>扣减余额</th><th>结果</th><th>说明</th><th>操作人</th></tr></thead>
          <tbody>
            <tr v-for="op in operations" :key="op.id">
              <td class="whitespace-nowrap text-xs">{{ formatDateTime(op.created_at) }}</td>
              <td>{{ Number(op.amount).toFixed(2) }}<span v-if="op.force" class="muted text-xs">（强制）</span></td>
              <td>{{ op.deduct_balance ? '是' : '否' }}</td>
              <td>{{ REFUND_RESULT_LABELS[op.result] || op.result }}</td>
              <td class="max-w-xs whitespace-normal text-xs">{{ op.message || '—' }}</td>
              <td class="text-xs">{{ op.operator_name || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
