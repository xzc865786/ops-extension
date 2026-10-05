<script setup lang="ts">
// Lets a user preview the orders they entered before submitting. Submission re-checks everything.
import { computed, ref, watch } from 'vue'
import api from '@/api/client'
import OrderTable, { type OrderRow } from '@/components/tickets/OrderTable.vue'
import { orderNosOf, type Kind } from '@/utils/ticketForm'

const props = defineProps<{ kind: Kind; value: unknown }>()

const rows = ref<OrderRow[]>([])
const checking = ref(false)
const nos = computed(() => orderNosOf(props.value))
const stale = ref(false)
watch(nos, () => { stale.value = rows.value.length > 0 })

async function check() {
  if (!nos.value.length || checking.value) return
  checking.value = true
  const result: OrderRow[] = []
  for (const no of nos.value) {
    try {
      const { data } = await api.get('/tickets/orders/lookup', { params: { kind: props.kind, out_trade_no: no } })
      result.push({ key: no, out_trade_no: no, order: data.order, note: data.problem || undefined })
    } catch (e: any) {
      const d = e.response?.data
      result.push({ key: no, out_trade_no: no, order: null, note: d?.detail?.detail || d?.detail || '查询失败' })
      if (e.response?.status === 429) break
    }
  }
  rows.value = result
  stale.value = false
  checking.value = false
}

const found = computed(() => rows.value.filter((r) => r.order))
const problems = computed(() => rows.value.filter((r) => r.note).length)
</script>

<template>
  <div class="space-y-2">
    <div class="flex flex-wrap items-center gap-3">
      <button type="button" class="btn-secondary btn-sm" :disabled="!nos.length || checking" @click="check">
        {{ checking ? '查询中…' : '查询订单' }}
      </button>
      <span v-if="!rows.length" class="muted text-xs">提交前可以先查询，确认订单金额和状态</span>
      <span v-else-if="stale" class="text-xs text-amber-700">订单号已修改，请重新查询</span>
      <span v-else-if="problems" class="text-xs text-red-600">有 {{ problems }} 个订单不能提交，请检查</span>
      <span v-else class="text-xs text-emerald-700">订单可以提交</span>
    </div>
    <OrderTable
      v-if="rows.length"
      :rows="rows"
      :show-invoice="kind === 'invoice' && found.length > 0"
    />
  </div>
</template>
