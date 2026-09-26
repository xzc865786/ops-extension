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
      class="pointer-events-auto flex items-start gap-2 rounded-xl border px-4 py-3 text-sm shadow-lg"
      :class="{
        'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-300': t.kind === 'success',
        'border-red-200 bg-red-50 text-red-800 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300': t.kind === 'error',
        'border-gray-200 bg-white text-gray-700 dark:border-dark-600 dark:bg-dark-800 dark:text-gray-200': t.kind === 'info',
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
