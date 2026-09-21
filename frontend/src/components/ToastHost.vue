<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { state, dismiss } = useToast()
</script>

<template>
  <div
    class="fixed z-[100] bottom-4 right-4 flex flex-col gap-2 max-w-sm w-[min(100vw-2rem,24rem)] pointer-events-none"
    aria-live="polite"
  >
    <div
      v-for="t in state.items"
      :key="t.id"
      class="pointer-events-auto rounded-lg border px-3 py-2 text-sm shadow-lg flex items-start gap-2"
      :class="{
        'bg-emerald-500/15 border-emerald-500/40 text-emerald-300': t.kind === 'success',
        'bg-red-500/15 border-red-500/40 text-red-300': t.kind === 'error',
        'bg-slate-800 border-slate-600 text-slate-200': t.kind === 'info',
      }"
    >
      <span class="flex-1 break-words">{{ t.message }}</span>
      <button
        type="button"
        class="shrink-0 text-xs opacity-70 hover:opacity-100"
        @click="dismiss(t.id)"
      >✕</button>
    </div>
  </div>
</template>
