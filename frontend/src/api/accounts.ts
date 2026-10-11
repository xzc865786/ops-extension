import api from './client'
import { errorText as ledgerErrorText } from './ledger'

export const accountsPath = '/admin/accounts'
export type AccountStatus = 'ACTIVE' | 'STANDBY' | 'BANNED' | 'DISABLED'
export type SecretField = 'password' | 'secret_notes'
export const accountStatusLabels: Record<AccountStatus, string> = { ACTIVE: '启用', STANDBY: '备用', BANNED: '封禁', DISABLED: '停用' }
export const ACCOUNT_STATUSES = Object.keys(accountStatusLabels) as AccountStatus[]

export interface Account {
  id: number; client: string; login: string; status: AccountStatus; status_label: string
  plan: string; expires_on: string | null; owner: string; phone: string; recovery_email: string; notes: string
  has_password: boolean; has_secret_notes: boolean; expiry: 'EXPIRED' | 'SOON' | null
  archived: boolean; version: number; created_at: string; updated_at: string
}
export interface AccountEvent { id: number; event_type: string; actor_name: string | null; actor_user_id: number; detail: any; created_at: string }
export interface AccountDetail extends Account { events: AccountEvent[] }
export interface AccountMeta { clients: string[]; owners: string[]; plans: string[]; vault_ready: boolean }

const fieldNames: Record<string, string> = { client: '客户端', login: '登录账号', status: '状态', plan: '套餐', expires_on: '到期日', owner: '使用人', phone: '绑定手机', recovery_email: '辅助邮箱', notes: '备注', password: '密码', secret_notes: '敏感备注', version: '记录版本' }
export const accountFieldLabels = fieldNames

export function errorText(error: any, fallback = '操作失败，请重试'): string {
  const detail = error.response?.data?.detail
  if (Array.isArray(detail)) return detail.map((d: any) => `${fieldNames[d.loc?.at(-1)] || '填写内容'}不符合要求，请检查必填项及长度`).join('；')
  return ledgerErrorText(error, fallback)
}

export async function revealSecret(id: number, field: SecretField, purpose: 'view' | 'copy'): Promise<string> {
  return (await api.post<{ value: string }>(`${accountsPath}/${id}/reveal`, { field, purpose })).data.value
}
