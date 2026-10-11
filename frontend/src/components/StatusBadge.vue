<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string; kind: 'ticket' | 'expense' | 'ledger' | 'account' }>()

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

const ledgerLabels: Record<string, string> = {
  PENDING: '待报销',
  REIMBURSED: '已报销',
  NOT_REQUIRED: '无需报销',
  VOIDED: '作废',
}

const accountLabels: Record<string, string> = {
  ACTIVE: '启用',
  STANDBY: '备用',
  BANNED: '封禁',
  DISABLED: '停用',
}

const label = computed(() =>
  ({ ticket: ticketLabels, expense: expenseLabels, ledger: ledgerLabels, account: accountLabels })[props.kind][props.status] ?? props.status,
)

const variant = computed(() => {
  if (props.kind === 'account') {
    return { ACTIVE: 'badge-success', STANDBY: 'badge-primary', BANNED: 'badge-danger' }[props.status] ?? 'badge-gray'
  }
  if (props.kind === 'ledger') {
    return { PENDING: 'badge-warning', REIMBURSED: 'badge-success', VOIDED: 'badge-danger' }[props.status] ?? 'badge-gray'
  }
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
