<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
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
  <div class="bg-white rounded shadow p-4 max-w-2xl">
    <h1 class="text-xl font-semibold mb-4">新建工单</h1>
    <p class="text-xs text-slate-500 mb-3">优先级固定为 P2（用户不可修改）</p>
    <form class="space-y-3" @submit.prevent="submit">
      <div>
        <label class="block text-sm mb-1">分类</label>
        <select v-model="form.category" class="border rounded w-full px-2 py-1.5">
          <option v-for="c in meta.categories" :key="c.value" :value="c.value">{{ c.label }}</option>
        </select>
      </div>
      <div>
        <label class="block text-sm mb-1">标题</label>
        <input v-model="form.title" required maxlength="200" class="border rounded w-full px-2 py-1.5" />
      </div>
      <div>
        <label class="block text-sm mb-1">描述</label>
        <textarea v-model="form.description" required rows="5" class="border rounded w-full px-2 py-1.5" />
      </div>
      <div>
        <label class="block text-sm mb-1">引用原工单号（可选）</label>
        <input v-model="form.ref_ticket_no" class="border rounded w-full px-2 py-1.5" placeholder="如 T202609210001" />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-sm mb-1">Request ID</label>
          <input v-model="form.request_id" class="border rounded w-full px-2 py-1.5" />
        </div>
        <div>
          <label class="block text-sm mb-1">模型名</label>
          <input v-model="form.model_name" class="border rounded w-full px-2 py-1.5" />
        </div>
      </div>
      <div>
        <label class="block text-sm mb-1">API Endpoint</label>
        <input v-model="form.api_endpoint" class="border rounded w-full px-2 py-1.5" />
      </div>
      <div>
        <label class="block text-sm mb-1">错误信息</label>
        <textarea v-model="form.error_message" rows="2" class="border rounded w-full px-2 py-1.5" />
      </div>
      <p v-if="error" class="text-red-600 text-sm">{{ error }}</p>
      <button
        type="submit"
        :disabled="saving"
        class="bg-sky-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
      >提交</button>
    </form>
  </div>
</template>
