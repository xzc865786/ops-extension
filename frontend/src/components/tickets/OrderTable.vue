<script setup lang="ts">
import { computed } from 'vue'
import { formatDateTime } from '@/utils/display'
import { ORDER_STATUS_LABELS, ORDER_TYPE_LABELS, type OrderSnapshot } from '@/utils/ticketForm'

export interface OrderRow {
  key: string | number
  out_trade_no: string
  order: OrderSnapshot | null
  /** Current state from Sub2API, shown next to the stored snapshot (admin). */
  live?: OrderSnapshot | null
  note?: string
  noteKind?: 'error' | 'muted'
}

const props = defineProps<{ rows: OrderRow[]; showInvoice?: boolean; showLive?: boolean; snapshot?: boolean }>()

const money = (o: OrderSnapshot | null | undefined, key: keyof OrderSnapshot) =>
  o && o[key] !== undefined ? `${o.currency === 'CNY' || !o.currency ? '¥' : `${o.currency} `}${o[key]}` : '—'
const status = (o: OrderSnapshot | null | undefined) => (o?.status ? ORDER_STATUS_LABELS[o.status] || o.status : '—')

const invoiceTotal = computed(() => {
  const cents = props.rows.reduce((sum, r) => sum + Math.round(Number(r.order?.invoiceable_amount || 0) * 100), 0)
  return (cents / 100).toFixed(2)
})
</script>

<template>
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>订单号</th>
          <th>实付金额</th>
          <th>到账额度</th>
          <th>类型</th>
          <th>支付时间</th>
          <th>{{ showLive || snapshot ? '提交时状态' : '状态' }}</th>
          <th v-if="showLive">当前状态</th>
          <th v-if="showInvoice">可开票金额</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="r in rows" :key="r.key">
          <tr>
            <td class="font-mono">{{ r.out_trade_no }}</td>
            <template v-if="r.order">
              <td>{{ money(r.order, 'pay_amount') }}</td>
              <td>
                {{ money(r.order, 'amount') }}
                <span v-if="Number(r.order.bonus_amount) > 0" class="muted text-xs">（赠送 {{ r.order.bonus_amount }}）</span>
              </td>
              <td>{{ ORDER_TYPE_LABELS[r.order.order_type || ''] || r.order.order_type || '—' }}</td>
              <td>{{ formatDateTime(r.order.paid_at) }}</td>
              <td>
                {{ status(r.order) }}
                <span v-if="Number(r.order.refund_amount) > 0" class="muted text-xs">（已退 {{ r.order.refund_amount }}）</span>
              </td>
            </template>
            <td v-else colspan="5" class="muted text-sm">{{ r.note ? '—' : '未校验（提交时未开启订单查询）' }}</td>
            <td v-if="showLive">
              <template v-if="r.live !== undefined">
                <span v-if="r.live">{{ status(r.live) }}<span v-if="Number(r.live.refund_amount) > 0" class="muted text-xs">（已退 {{ r.live.refund_amount }}）</span></span>
                <span v-else class="text-red-600">Sub2API 中找不到</span>
              </template>
              <span v-else class="muted">—</span>
            </td>
            <td v-if="showInvoice">{{ money(r.order, 'invoiceable_amount') }}</td>
          </tr>
          <tr v-if="r.note">
            <td :colspan="6 + (showLive ? 1 : 0) + (showInvoice ? 1 : 0)" class="pt-0 text-xs"
                :class="r.noteKind === 'muted' ? 'muted' : 'text-red-600'">{{ r.note }}</td>
          </tr>
        </template>
      </tbody>
      <tfoot v-if="showInvoice && rows.length > 1">
        <tr>
          <td :colspan="6 + (showLive ? 1 : 0)" class="px-4 py-2 text-right text-sm font-medium">合计可开票</td>
          <td class="px-4 py-2 text-sm font-medium">¥{{ invoiceTotal }}</td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>
