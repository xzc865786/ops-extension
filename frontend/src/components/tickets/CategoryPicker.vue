<script setup lang="ts">
import type { FormCategory } from '@/utils/ticketForm'

defineProps<{ categories: FormCategory[] }>()
const model = defineModel<string>()
</script>

<template>
  <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4" role="radiogroup" aria-label="工单分类">
    <button
      v-for="c in categories"
      :key="c.key"
      type="button"
      role="radio"
      :aria-checked="model === c.key"
      class="rounded-xl border px-3 py-2.5 text-left transition-colors"
      :class="model === c.key
        ? 'border-primary-500 bg-primary-50 ring-1 ring-primary-500 dark:bg-primary-900/20'
        : 'border-gray-200 bg-white hover:border-gray-300 dark:border-dark-600 dark:bg-dark-800 dark:hover:border-dark-500'"
      @click="model = c.key"
    >
      <span class="block text-sm font-medium text-gray-900 dark:text-white">{{ c.label }}</span>
      <span v-if="c.description" class="muted mt-0.5 block text-xs leading-snug">{{ c.description }}</span>
    </button>
  </div>
</template>
