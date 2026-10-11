<script setup lang="ts">
import { nextTick, onMounted, ref, useTemplateRef } from 'vue'

// In-page replacement for window.prompt, which sandboxed iframes may silently block.
const props = withDefaults(defineProps<{ title: string; description?: string; confirmText?: string; busy?: boolean; error?: string }>(), { confirmText: '确认' })
const emit = defineEmits<{ confirm: [reason: string]; cancel: [] }>()
const reason = ref('')
const input = useTemplateRef<HTMLTextAreaElement>('input')
onMounted(() => nextTick(() => input.value?.focus()))
function submit() { if (reason.value.trim() && !props.busy) emit('confirm', reason.value.trim()) }
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/40 p-4" @keydown.esc="emit('cancel')">
    <form class="card card-body w-full max-w-md space-y-4 dark:!bg-dark-800" role="dialog" aria-modal="true" :aria-label="title" @submit.prevent="submit">
      <h2 class="section-title">{{ title }}</h2>
      <p v-if="description" class="text-sm muted whitespace-pre-line">{{ description }}</p>
      <p v-if="error" class="alert-error" role="alert">{{ error }}</p>
      <div><label for="reason-dialog-input" class="input-label">原因</label><textarea id="reason-dialog-input" ref="input" v-model="reason" class="input" rows="3" maxlength="2000" required /></div>
      <div class="flex justify-end gap-2">
        <button type="button" class="btn-ghost" :disabled="busy" @click="emit('cancel')">取消</button>
        <button class="btn-danger" :disabled="busy || !reason.trim()">{{ busy ? '正在处理…' : confirmText }}</button>
      </div>
    </form>
  </div>
</template>
