<script setup lang="ts">
import { useToast } from '@/composables/useToast'
import { downloadAttachment } from '@/utils/attachments'
import { formatDateTime } from '@/utils/display'
import { RESOLUTION_SOURCE_LABELS } from '@/utils/ticketForm'

defineProps<{ resolution: Record<string, any>; admin?: boolean }>()
const toast = useToast()

const money = (value: string, currency?: string) => (!currency || currency === 'CNY' ? `¥${value}` : `${currency} ${value}`)

async function download(id: number, name: string) {
  try {
    await downloadAttachment(id, name)
  } catch (e: any) {
    toast.error(e.message || '下载失败')
  }
}
</script>

<template>
  <div class="space-y-2 text-sm">
    <template v-if="resolution.outcome === 'REFUNDED'">
      <p class="flex items-center gap-2"><span class="badge-success">已退款</span>
        原路退回 <strong>{{ money(resolution.gateway_amount, resolution.currency) }}</strong>
      </p>
      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
        <template v-if="resolution.out_trade_no"><dt class="muted">订单号</dt><dd class="font-mono">{{ resolution.out_trade_no }}</dd></template>
        <dt class="muted">退款额度</dt><dd>{{ resolution.refund_amount }}</dd>
        <template v-if="resolution.balance_deducted"><dt class="muted">扣减余额</dt><dd>{{ resolution.balance_deducted }}</dd></template>
        <template v-if="resolution.subscription_days_deducted"><dt class="muted">扣减订阅</dt><dd>{{ resolution.subscription_days_deducted }} 天</dd></template>
        <template v-if="admin && resolution.source"><dt class="muted">方式</dt><dd>{{ RESOLUTION_SOURCE_LABELS[resolution.source] || resolution.source }}</dd></template>
        <template v-if="admin && resolution.note"><dt class="muted">备注</dt><dd>{{ resolution.note }}</dd></template>
      </dl>
    </template>
    <template v-else-if="resolution.outcome === 'REJECTED'">
      <p class="flex items-center gap-2"><span class="badge-danger">未通过</span></p>
      <p class="whitespace-pre-wrap">{{ resolution.reason }}</p>
    </template>
    <template v-else-if="resolution.outcome === 'ISSUED'">
      <p class="flex items-center gap-2"><span class="badge-success">已开票</span></p>
      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
        <dt class="muted">发票号码</dt><dd class="font-mono">{{ resolution.invoice_no }}</dd>
        <dt class="muted">开票日期</dt><dd>{{ resolution.issued_on }}</dd>
        <dt class="muted">金额</dt><dd>¥{{ resolution.amount }}</dd>
        <template v-if="resolution.email"><dt class="muted">已发送至</dt><dd>{{ resolution.email }}</dd></template>
      </dl>
      <button v-if="resolution.attachment_id" type="button" class="btn-secondary btn-sm" @click="download(resolution.attachment_id, resolution.file_name)">
        下载发票
      </button>
    </template>
    <p class="muted text-xs">
      {{ formatDateTime(resolution.at) }}<template v-if="admin && resolution.operator_name"> · {{ resolution.operator_name }}</template>
    </p>
  </div>
</template>
