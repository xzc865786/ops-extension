// Per-category ticket forms. The backend (app/tickets/form_schema.py) is the source of truth for
// validation; the checks here only give early feedback.
import { formatDateTime } from '@/utils/display'

export type FieldType =
  | 'text' | 'textarea' | 'number' | 'money' | 'select' | 'radio' | 'confirm'
  | 'date' | 'datetime' | 'email' | 'order_no' | 'order_no_list'

export type Kind = 'general' | 'refund' | 'invoice' | 'payment'

export interface FormOption { value: string; label: string }

export interface ShowIf { field: string; equals?: string | boolean; in?: string[] }

export interface FormField {
  key: string
  label: string
  type: FieldType
  required?: boolean
  system?: boolean
  help?: string
  placeholder?: string
  max_length?: number | null
  min?: number | null
  max?: number | null
  options?: FormOption[]
  show_if?: ShowIf | null
}

export interface FormCategory {
  key: string
  label: string
  description?: string
  kind: Kind
  enabled: boolean
  notice?: string
  title_mode: 'required' | 'optional' | 'auto'
  title_template?: string
  description_mode: 'required' | 'optional' | 'hidden'
  require_attachment?: boolean
  attachment_hint?: string
  fields: FormField[]
}

/** Snapshot stored on each ticket. */
export interface FormSchema { key: string; label: string; kind: Kind; fields: FormField[] }

export const FIELD_TYPES: { value: FieldType; label: string }[] = [
  { value: 'text', label: '单行文字' },
  { value: 'textarea', label: '多行文字' },
  { value: 'number', label: '数字' },
  { value: 'money', label: '金额' },
  { value: 'select', label: '下拉选择' },
  { value: 'radio', label: '单选' },
  { value: 'confirm', label: '勾选确认' },
  { value: 'date', label: '日期' },
  { value: 'datetime', label: '日期时间' },
  { value: 'email', label: '邮箱' },
  { value: 'order_no', label: '订单号' },
  { value: 'order_no_list', label: '多个订单号' },
]

export const KIND_LABELS: Record<Kind, string> = {
  general: '普通',
  refund: '退款',
  invoice: '开票',
  payment: '充值/支付',
}

export const BUILTIN_CATEGORIES = [
  'API_ERROR', 'AUTH_ERROR', 'BILLING_ERROR', 'RECHARGE_PAYMENT', 'INVOICE', 'REFUND',
  'MODEL_AVAILABILITY', 'RATE_LIMIT', 'ACCOUNT', 'FEATURE_REQUEST', 'OTHER',
]

export const MAX_ORDER_NOS = 10
export const CATEGORY_KEY_RE = /^[A-Z][A-Z0-9_]{1,39}$/
export const FIELD_KEY_RE = /^[a-z][a-z0-9_]{0,39}$/

export const fieldTypeLabel = (type: FieldType) => FIELD_TYPES.find((t) => t.value === type)?.label || type

export function isVisible(field: FormField, values: Record<string, any>): boolean {
  const cond = field.show_if
  if (!cond) return true
  const value = values[cond.field]
  if (cond.in) return cond.in.includes(value)
  return value === cond.equals
}

export function emptyValue(field: FormField): any {
  return field.type === 'confirm' ? false : ''
}

export function initialValues(fields: FormField[]): Record<string, any> {
  return Object.fromEntries(fields.map((f) => [f.key, emptyValue(f)]))
}

function isEmpty(value: any): boolean {
  return value === null || value === undefined || value === false || (typeof value === 'string' && !value.trim())
    || (Array.isArray(value) && !value.length)
}

export function splitOrderNos(value: string): string[] {
  return [...new Set(value.split(/[\s,，、;；]+/).map((s) => s.trim()).filter(Boolean))]
}

/** Values of the visible fields only, as sent to the backend. */
export function collectValues(fields: FormField[], values: Record<string, any>): Record<string, any> {
  const out: Record<string, any> = {}
  for (const f of fields) {
    if (!isVisible(f, out) || isEmpty(values[f.key])) continue
    out[f.key] = values[f.key]
  }
  return out
}

export function localErrors(fields: FormField[], values: Record<string, any>): Record<string, string> {
  const errors: Record<string, string> = {}
  const visible: Record<string, any> = {}
  for (const f of fields) {
    if (!isVisible(f, visible)) continue
    const value = values[f.key]
    visible[f.key] = value
    if (isEmpty(value)) {
      if (f.required) errors[f.key] = f.type === 'confirm' ? '请勾选' : '必填'
      continue
    }
    if (f.type === 'order_no_list' && splitOrderNos(String(value)).length > MAX_ORDER_NOS) {
      errors[f.key] = `最多 ${MAX_ORDER_NOS} 个订单号`
    }
    if (f.type === 'money' && !/^\d+(\.\d{1,2})?$/.test(String(value).trim())) {
      errors[f.key] = '金额最多两位小数'
    }
  }
  return errors
}

export function displayValue(field: FormField, value: any): string {
  if (field.type === 'select' || field.type === 'radio') {
    return field.options?.find((o) => o.value === value)?.label || String(value)
  }
  if (Array.isArray(value)) return value.join('、')
  if (value === true) return '是'
  if (field.type === 'datetime' && typeof value === 'string') {
    // Values typed into datetime-local are stored as Beijing time without an offset.
    return /(Z|[+-]\d{2}:?\d{2})$/.test(value) ? formatDateTime(value) : value.replace('T', ' ')
  }
  if (field.type === 'money') return `¥${value}`
  return String(value)
}
