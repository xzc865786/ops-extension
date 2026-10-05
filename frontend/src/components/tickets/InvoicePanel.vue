<script setup lang="ts">
// Admin handling of an invoice ticket: record the issued invoice (number, date, amount, PDF) or reject.
import { computed, reactive, ref } from 'vue'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'
import ResolutionView from '@/components/tickets/ResolutionView.vue'

const props = defineProps<{ ticket: any }>()
const emit = defineEmits<{ updated: [ticket: any]; reload: [] }>()
const toast = useToast()

const rows = computed<any[]>(() => (props.ticket.orders || []).filter((o: any) => o.purpose === 'INVOICE'))
const verified = computed(() => rows.value.length > 0 && rows.value.every((o) => o.snapshot))
const total = computed(() => (rows.value.reduce((sum, o) => sum + Math.round(Number(o.snapshot?.invoiceable_amount || 0) * 100), 0) / 100).toFixed(2))
const pdfs = computed<any[]>(() => (props.ticket.attachments || []).filter((a: any) => a.mime_type === 'application/pdf'))
const email = computed(() => props.ticket.form_data?.email || '')
const closed = computed(() => props.ticket.status === 'CLOSED')

const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
const form = reactive({
  invoice_no: '',
  issued_on: today,
  amount: verified.value ? total.value : '',
  attachment_id: (pdfs.value[pdfs.value.length - 1]?.id ?? null) as number | null,
  emailed: false,
})
const busy = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const showReject = ref(false)
const rejectReason = ref('')

function errMsg(e: any, fallback: string) {
  const d = e.response?.data
  return d?.detail?.detail || (typeof d?.detail === 'string' ? d.detail : '') || fallback
}

async function upload() {
  const file = fileInput.value?.files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    toast.error('发票文件须为 PDF')
    return
  }
  uploading.value = true
  try {
    const body = new FormData()
    body.append('file', file)
    const { data } = await api.post(`/admin/tickets/${props.ticket.id}/attachments`, body)
    form.attachment_id = data.id
    emit('reload')
    toast.success('发票文件已上传')
  } catch (e: any) {
    toast.error(errMsg(e, '上传失败'))
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function submit() {
  busy.value = true
  try {
    const { data } = await api.post(`/admin/tickets/${props.ticket.id}/invoice`, {
      ...form, invoice_no: form.invoice_no.trim(), amount: String(form.amount).trim(),
    })
    emit('updated', data)
    toast.success('已登记发票并回复用户')
  } catch (e: any) {
    const d = e.response?.data
    toast.error(Array.isArray(d?.detail) ? '请把发票信息填写完整' : errMsg(e, '登记失败'))
  } finally {
    busy.value = false
  }
}

async function reject() {
  if (!rejectReason.value.trim()) {
    toast.error('请填写驳回原因')
    return
  }
  busy.value = true
  try {
    const { data } = await api.post(`/admin/tickets/${props.ticket.id}/reject`, { reason: rejectReason.value.trim() })
    emit('updated', data)
    toast.success('已驳回并回复用户')
  } catch (e: any) {
    toast.error(errMsg(e, '驳回失败'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="card space-y-4 p-5 sm:p-6">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="section-title">开票处理</h2>
      <span v-if="verified" class="muted text-sm">· 可开票金额 ¥{{ total }}</span>
    </div>

    <ResolutionView v-if="ticket.resolution" :resolution="ticket.resolution" admin />

    <template v-else-if="!closed">
      <p class="muted text-sm">在税务平台开具电子普通发票并发送到收票邮箱后，在这里登记。用户会收到回复，并能在工单附件中下载发票。</p>
      <div class="grid gap-4 sm:grid-cols-3">
        <div>
          <label class="input-label" for="inv-no">发票号码</label>
          <input id="inv-no" v-model="form.invoice_no" class="input font-mono" maxlength="40" />
        </div>
        <div>
          <label class="input-label" for="inv-date">开票日期</label>
          <input id="inv-date" v-model="form.issued_on" type="date" class="input" :max="today" />
        </div>
        <div>
          <label class="input-label" for="inv-amount">开票金额 <span v-if="verified" class="muted font-normal">（不超过 {{ total }}）</span></label>
          <input id="inv-amount" v-model="form.amount" class="input" inputmode="decimal" />
        </div>
      </div>
      <div>
        <p class="input-label">发票文件（PDF）</p>
        <div class="flex flex-wrap items-center gap-2">
          <select v-if="pdfs.length" v-model="form.attachment_id" class="input sm:max-w-xs">
            <option v-for="a in pdfs" :key="a.id" :value="a.id">{{ a.file_name }}</option>
          </select>
          <label class="file-picker">
            <span class="file-picker-btn">{{ uploading ? '上传中…' : '上传 PDF' }}</span>
            <input ref="fileInput" type="file" class="sr-only" accept=".pdf" :disabled="uploading" @change="upload" />
          </label>
        </div>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="form.emailed" type="checkbox" /> 已将发票发送至 <span class="font-medium">{{ email || '收票邮箱' }}</span>
      </label>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn-primary" :disabled="busy || !form.invoice_no || !form.amount || !form.attachment_id || !form.emailed" @click="submit">
          登记开票
        </button>
        <button v-if="!showReject" type="button" class="btn-ghost text-red-600" @click="showReject = true">驳回申请</button>
      </div>
      <div v-if="showReject" class="space-y-2 border-t pt-3">
        <label class="input-label" for="inv-reject">驳回原因（会回复给用户）</label>
        <textarea id="inv-reject" v-model="rejectReason" class="input" rows="2" maxlength="500" />
        <div class="flex gap-2">
          <button type="button" class="btn-danger btn-sm" :disabled="busy" @click="reject">确认驳回</button>
          <button type="button" class="btn-secondary btn-sm" @click="showReject = false">取消</button>
        </div>
      </div>
    </template>
    <p v-else class="muted text-sm">工单已关闭。</p>
  </section>
</template>
