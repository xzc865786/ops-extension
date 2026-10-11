<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { errorText, revealSecret, type SecretField } from '@/api/accounts'
import { useToast } from '@/composables/useToast'

// Plaintext stays on screen for this long, then is dropped from memory.
const VISIBLE_SECONDS = 30
const props = defineProps<{ accountId: number; field: SecretField; label: string; present: boolean; multiline?: boolean }>()
const toast = useToast()
const value = ref<string | null>(null), left = ref(0), busy = ref(false), copyFailed = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
function hide() { clearInterval(timer); value.value = null; left.value = 0; copyFailed.value = false }
onBeforeUnmount(hide)
function show(plaintext: string) {
  hide(); value.value = plaintext; left.value = VISIBLE_SECONDS
  timer = setInterval(() => { if (--left.value <= 0) hide() }, 1000)
}
async function reveal(purpose: 'view' | 'copy') {
  if (busy.value) return
  busy.value = true
  try {
    const plaintext = await revealSecret(props.accountId, props.field, purpose)
    if (purpose === 'view') return show(plaintext)
    try { await navigator.clipboard.writeText(plaintext); toast.success(`已复制${props.label}`) }
    // Embedded frames may lack clipboard permission: fall back to showing it for manual copying.
    catch { show(plaintext); copyFailed.value = true }
  } catch (e) { toast.error(errorText(e)) } finally { busy.value = false }
}
</script>

<template>
  <span v-if="!present" class="muted">—</span>
  <span v-else class="inline-flex max-w-full flex-wrap items-center gap-2">
    <template v-if="value !== null">
      <code :class="multiline ? 'whitespace-pre-wrap' : 'whitespace-pre'" class="select-all break-all rounded-md bg-gray-100 px-2 py-0.5 text-sm dark:bg-dark-700">{{ value }}</code>
      <span class="text-xs muted tabular-nums">{{ copyFailed ? '无法自动复制，请手动选择复制 · ' : '' }}{{ left }} 秒后隐藏</span>
      <button type="button" class="link text-xs" @click="hide">隐藏</button>
    </template>
    <template v-else>
      <span class="tracking-widest muted" aria-hidden="true">••••••</span>
      <button type="button" class="link text-xs" :disabled="busy" :aria-label="`查看${label}`" @click="reveal('view')">查看</button>
      <button type="button" class="link text-xs" :disabled="busy" :aria-label="`复制${label}`" @click="reveal('copy')">复制</button>
    </template>
  </span>
</template>
