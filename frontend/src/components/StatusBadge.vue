<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string; kind: 'ticket' | 'expense' }>()

const ticketLabels: Record<string, string> = {
  OPEN: '待处理',
  PROCESSING: '处理中',
  WAITING_USER: '等待用户',
  RESOLVED: '已解决',
  CLOSED: '已关闭',
}

const expenseLabels: Record<string, string> = {
  DRAFT: '草稿',
  SUBMITTED: '待审批',
  APPROVED: '已审批',
  REJECTED: '已驳回',
  PAID: '已付款',
  CANCELLED: '已取消',
}

const label = computed(() =>
  (props.kind === 'ticket' ? ticketLabels : expenseLabels)[props.status] ?? props.status,
)

const variant = computed(() => {
  if (['RESOLVED', 'PAID', 'APPROVED'].includes(props.status)) return 'badge-success'
  if (['PROCESSING', 'SUBMITTED'].includes(props.status)) return 'badge-primary'
  if (props.status === 'WAITING_USER') return 'badge-warning'
  if (props.status === 'REJECTED') return 'badge-danger'
  return 'badge-gray'
})
</script>

<template>
  <span :class="variant">{{ label }}</span>
</template>
