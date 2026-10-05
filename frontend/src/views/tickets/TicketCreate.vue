<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { useToast } from '@/composables/useToast'
import CategoryPicker from '@/components/tickets/CategoryPicker.vue'
import DynamicForm from '@/components/tickets/DynamicForm.vue'
import OrderCheck from '@/components/tickets/OrderCheck.vue'
import { ORDER_FIELDS, collectValues, initialValues, localErrors, type FormCategory } from '@/utils/ticketForm'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const formVersion = ref<number | null>(null)
const orderLookup = ref(false)
const categories = ref<FormCategory[]>([])
const categoryKey = ref('')
const values = reactive<Record<string, any>>({})
const fieldErrors = ref<Record<string, string>>({})
const form = reactive({ title: '', description: '', ref_ticket_no: '' })
const files = ref<File[]>([])
const error = ref('')
const saving = ref(false)
const loadError = ref('')

const category = computed(() => categories.value.find((c) => c.key === categoryKey.value) || null)
const orderField = computed(() => (category.value ? ORDER_FIELDS[category.value.kind] : undefined))

onMounted(async () => {
  try {
    const { data } = await api.get('/tickets/meta')
    formVersion.value = data.form_version
    orderLookup.value = !!data.order_lookup
    categories.value = data.categories.filter((c: FormCategory) => c.enabled)
    const wanted = String(route.query.category || '')
    if (categories.value.some((c) => c.key === wanted)) categoryKey.value = wanted
  } catch {
    loadError.value = '加载工单分类失败，请刷新重试'
  }
})

watch(category, (c) => {
  const next = initialValues(c?.fields || [])
  for (const key of Object.keys(values)) delete values[key]
  Object.assign(values, next)
  fieldErrors.value = {}
  error.value = ''
})

// Once a flagged field is fixed, drop its message without waiting for the next submit.
watch(values, () => {
  const c = category.value
  if (!c || !Object.keys(fieldErrors.value).length) return
  const current = localErrors(c.fields, values)
  fieldErrors.value = Object.fromEntries(Object.keys(fieldErrors.value).filter((k) => current[k]).map((k) => [k, current[k]]))
})

function onFiles(event: Event) {
  const input = event.target as HTMLInputElement
  files.value = [...files.value, ...Array.from(input.files || [])].slice(0, 5)
  input.value = ''
}

function errMsg(e: any, fallback: string) {
  const d = e.response?.data
  return d?.detail?.detail || (typeof d?.detail === 'string' ? d.detail : '') || fallback
}

async function submit() {
  const c = category.value
  if (!c || saving.value) return
  error.value = ''
  fieldErrors.value = localErrors(c.fields, values)
  const problems: string[] = []
  if (Object.keys(fieldErrors.value).length) problems.push('请检查标红的字段')
  if (c.title_mode === 'required' && !form.title.trim()) problems.push('请填写标题')
  if (c.description_mode === 'required' && !form.description.trim()) problems.push('请填写问题描述')
  if (c.require_attachment && !files.value.length) problems.push('这个分类需要上传附件')
  if (problems.length) {
    error.value = problems.join('；')
    return
  }
  saving.value = true
  try {
    const { data } = await api.post('/tickets', {
      category: c.key,
      form_version: formVersion.value,
      form_data: collectValues(c.fields, values),
      title: c.title_mode === 'auto' ? null : form.title.trim() || null,
      description: c.description_mode === 'hidden' ? null : form.description.trim() || null,
      ref_ticket_no: form.ref_ticket_no.trim() || null,
    })
    let failed = 0
    for (const file of files.value) {
      const body = new FormData()
      body.append('file', file)
      try {
        await api.post(`/tickets/${data.id}/attachments`, body)
      } catch {
        failed += 1
      }
    }
    if (failed) toast.error(`工单已提交，但有 ${failed} 个附件上传失败，请在详情页重新上传`)
    else toast.success('工单已提交')
    router.push(`/tickets/${data.id}`)
  } catch (e: any) {
    error.value = errMsg(e, '创建失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="card max-w-3xl p-5 sm:p-6">
    <RouterLink to="/tickets" class="link mb-2 inline-block text-sm">← 返回我的工单</RouterLink>
    <h1 class="page-title mb-4">新建工单</h1>
    <p v-if="loadError" class="alert-error">{{ loadError }}</p>

    <form class="space-y-5" @submit.prevent="submit">
      <section>
        <h2 class="input-label">选择问题类型</h2>
        <CategoryPicker v-model="categoryKey" :categories="categories" />
      </section>

      <template v-if="category">
        <p
          v-if="category.notice"
          class="whitespace-pre-wrap rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 text-sm text-primary-800 dark:border-primary-900/50 dark:bg-primary-900/20 dark:text-primary-300"
        >{{ category.notice }}</p>

        <div v-if="category.title_mode !== 'auto'">
          <label class="input-label" for="ticket-title">
            标题<span v-if="category.title_mode === 'required'" class="text-red-500"> *</span>
            <span v-else class="muted font-normal">（可选，留空自动生成）</span>
          </label>
          <input id="ticket-title" v-model="form.title" maxlength="200" class="input" />
        </div>

        <DynamicForm :fields="category.fields" :values="values" :errors="fieldErrors" />
        <OrderCheck v-if="orderLookup && orderField" :key="category.key" :kind="category.kind" :value="values[orderField]" />

        <div v-if="category.description_mode !== 'hidden'">
          <label class="input-label" for="ticket-desc">
            {{ category.fields.length ? '补充说明' : '问题描述' }}<span v-if="category.description_mode === 'required'" class="text-red-500"> *</span>
            <span v-else class="muted font-normal">（可选）</span>
          </label>
          <textarea id="ticket-desc" v-model="form.description" rows="4" class="input" />
        </div>

        <div>
          <p class="input-label">
            附件<span v-if="category.require_attachment" class="text-red-500"> *</span>
            <span class="muted font-normal">（最多 5 个，单个 ≤20MB，图片 / PDF / 日志）</span>
          </p>
          <p v-if="category.attachment_hint" class="muted mb-2 text-xs">{{ category.attachment_hint }}</p>
          <label class="file-picker">
            <span class="file-picker-btn">选择文件</span>
            <span class="file-picker-name">{{ files.length ? `已选 ${files.length} 个` : '未选择文件' }}</span>
            <input type="file" class="sr-only" multiple accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,.log,.txt" @change="onFiles" />
          </label>
          <ul v-if="files.length" class="mt-2 space-y-1 text-sm">
            <li v-for="(f, i) in files" :key="i" class="flex items-center gap-2">
              <span class="break-all">{{ f.name }}</span>
              <button type="button" class="btn-ghost btn-sm" @click="files.splice(i, 1)">移除</button>
            </li>
          </ul>
        </div>

        <div>
          <label class="input-label" for="ref-no">引用原工单号 <span class="muted font-normal">（可选）</span></label>
          <input id="ref-no" v-model="form.ref_ticket_no" class="input sm:max-w-xs" placeholder="如 T202609210001" />
        </div>

        <p v-if="error" class="alert-error">{{ error }}</p>
        <div class="flex items-center gap-3">
          <button type="submit" :disabled="saving" class="btn-primary">{{ saving ? '提交中…' : '提交' }}</button>
          <span class="muted text-xs">优先级固定为 P2；提交后标题与内容不可修改，可通过回复补充。</span>
        </div>
      </template>
    </form>
  </div>
</template>
