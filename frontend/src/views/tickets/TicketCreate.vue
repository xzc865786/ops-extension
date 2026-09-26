<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import api from '@/api/client'

const router = useRouter()
const meta = ref<any>({ categories: [] })
const form = reactive({
  title: '',
  description: '',
  category: 'OTHER',
  ref_ticket_no: '',
  request_id: '',
  model_name: '',
  api_endpoint: '',
  error_message: '',
})
const error = ref('')
const saving = ref(false)

onMounted(async () => {
  const { data } = await api.get('/tickets/meta')
  meta.value = data
  if (data.categories?.length) form.category = data.categories[0].value
})

async function submit() {
  error.value = ''
  saving.value = true
  try {
    const payload: any = { ...form }
    if (!payload.ref_ticket_no) delete payload.ref_ticket_no
    const { data } = await api.post('/tickets', payload)
    router.push(`/tickets/${data.id}`)
  } catch (e: any) {
    error.value = e.response?.data?.detail?.detail || e.response?.data?.detail || '创建失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="card p-5 sm:p-6 max-w-3xl">
    <RouterLink to="/tickets" class="link mb-2 inline-block text-sm">← 返回我的工单</RouterLink>
    <h1 class="page-title mb-4">新建工单</h1>
    <p class="text-xs muted mb-3">优先级固定为 P2（用户不可修改）</p>
    <form class="space-y-5" @submit.prevent="submit">
      <div>
        <label class="input-label">分类</label>
        <select v-model="form.category" class="input">
          <option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option>
        </select>
      </div>
      <div>
        <label class="input-label">标题</label>
        <input v-model="form.title" required maxlength="200" class="input" />
      </div>
      <div>
        <label class="input-label">描述</label>
        <textarea v-model="form.description" required rows="5" class="input" />
      </div>
      <div>
        <label class="input-label">引用原工单号（可选）</label>
        <input v-model="form.ref_ticket_no" class="input" placeholder="如 T202609210001" />
      </div>
      <div class="border-t pt-5">
        <h2 class="section-title mb-3">问题定位信息</h2>
        <div class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="input-label">Request ID</label>
              <input v-model="form.request_id" class="input" />
            </div>
            <div>
              <label class="input-label">模型名</label>
              <input v-model="form.model_name" class="input" />
            </div>
          </div>
          <div>
            <label class="input-label">API Endpoint</label>
            <input v-model="form.api_endpoint" class="input" />
          </div>
          <div>
            <label class="input-label">错误信息</label>
            <textarea v-model="form.error_message" rows="2" class="input" />
          </div>
        </div>
      </div>
      <p v-if="error" class="alert-error">{{ error }}</p>
      <button
        type="submit"
        :disabled="saving"
        class="btn-primary"
      >提交</button>
    </form>
  </div>
</template>
