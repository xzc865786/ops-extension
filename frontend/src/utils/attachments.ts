import api from '@/api/client'

async function downloadError(error: any): Promise<Error> {
  let detail = error.response?.data
  if (detail instanceof Blob) {
    try {
      detail = JSON.parse(await detail.text())
    } catch {
      detail = null
    }
  }
  const code = detail?.code || detail?.detail?.code
  if (code === 'ATTACHMENT_OBJECT_MISSING') {
    return new Error('附件文件不存在，请联系管理员恢复或重新上传')
  }
  if (code === 'ATTACHMENT_STORAGE_UNAVAILABLE') {
    return new Error('附件存储暂不可用，请稍后重试')
  }
  const message = typeof detail?.detail === 'string' ? detail.detail : detail?.detail?.detail
  return new Error(message || '附件下载失败，请稍后重试')
}

export async function downloadAttachment(id: number, filename: string, source: 'ticket' | 'expense' = 'ticket') {
  let blob: Blob
  try {
    const response = await api.get<Blob>(`/attachments/${id}/download`, {
      params: { source, proxy: true },
      responseType: 'blob',
    })
    blob = response.data
  } catch (error) {
    throw await downloadError(error)
  }

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
