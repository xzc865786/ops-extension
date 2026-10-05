export interface LabelOption {
  value: string
  label: string
}

export function labelFor(options: LabelOption[] | undefined, value: string | null | undefined): string {
  if (!value) return '—'
  return options?.find(option => option.value === value)?.label || value
}

export const TICKET_EVENT_LABELS: Record<string, string> = {
  CREATED: '创建工单',
  CLAIMED: '认领',
  UNCLAIMED: '释放',
  TAKEN_OVER: '接管',
  STATUS_CHANGED: '状态变更',
  PRIORITY_CHANGED: '优先级变更',
  CATEGORY_CHANGED: '分类变更',
  USER_REPLIED: '用户回复',
  ADMIN_REPLIED: '管理员回复',
  INTERNAL_NOTE_ADDED: '内部备注',
  ATTACHMENT_ADDED: '上传附件',
  CLOSED_BY_USER: '用户关闭',
  CLOSED_BY_ADMIN: '管理员关闭',
  REF_TICKET_LINKED: '引用原工单',
  REFUND_SUBMITTED: '发起退款',
  REFUND_SUCCEEDED: '退款成功',
  REFUND_PENDING: '退款处理中',
  REFUND_FAILED: '退款失败',
  REFUND_REGISTERED: '登记退款',
  INVOICE_ISSUED: '登记开票',
  REQUEST_REJECTED: '驳回申请',
}

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date)
}
