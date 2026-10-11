import api from './client'
export const ledgerPath = '/admin/expense-records'
export const statusLabels: Record<string, string> = { PENDING: '待报销', REIMBURSED: '已报销', NOT_REQUIRED: '无需报销', VOIDED: '作废' }
export interface ExpenseRecord {
  id: number; title: string; expense_date: string; category: string; category_label: string; payer: string; merchant: string
  currency: 'CNY' | 'USD'; amount: string; rmb_amount: string; amount_mode: 'AUTO' | 'MANUAL'
  quote_id: string | null; reference_rate: string | null; rate_date: string | null; rate_fetched_at: string | null; rate_source: string | null
  needs_reimbursement: boolean; active: boolean; notes: string; version: number; status: string; created_by: number
  batch_id: number | null; reimbursement_date: string | null; actual_reimbursement: string | null; difference: string | null; legacy_claim_id: number | null
}
export function errorText(error: any, fallback = '操作失败，请重试'): string {
  const detail = error.response?.data?.detail
  if (Array.isArray(detail)) {
    const fields: Record<string,string> = { title:'购买内容', expense_date:'支出日期', category:'分类', payer:'付款人', merchant:'商家', currency:'币种', amount:'原币金额', rmb_amount:'人民币金额', reimbursement_date:'报销日期', actual_amount:'实际报销金额', difference_reason:'差额说明', notes:'备注', version:'记录版本', records:'所选支出' }
    return detail.map((d: any) => {
      const field = fields[d.loc?.at(-1)] || '填写内容'
      return /^Value error, /.test(d.msg) ? d.msg.replace(/^Value error, /, '') : `${field}不符合要求，请检查格式、必填项及长度`
    }).join('；')
  }
  return typeof detail === 'string' ? detail : detail?.detail || error.message || fallback
}
export async function uploadProof(path: string, file: File) {
  const form = new FormData(); form.append('file', file)
  await api.post(path + '/attachments', form)
}
export async function exportLedger(params: Record<string, unknown>) {
  const { data } = await api.get(ledgerPath + '/export', { params, responseType: 'blob' })
  const url = URL.createObjectURL(data), a = document.createElement('a')
  a.href = url; a.download = '月度开支.xlsx'; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
