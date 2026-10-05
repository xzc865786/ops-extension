<script setup lang="ts">
// Read-only view of a ticket's form values, labelled by the snapshot taken when it was submitted.
import { computed } from 'vue'
import { displayValue, type FormSchema } from '@/utils/ticketForm'

const props = defineProps<{ schema: FormSchema | null; data: Record<string, any> | null }>()

const rows = computed(() => {
  const data = props.data || {}
  const fields = props.schema?.fields || []
  const known = new Set(fields.map((f) => f.key))
  const rows = fields
    .filter((f) => data[f.key] !== undefined && data[f.key] !== null && data[f.key] !== '')
    .map((f) => ({ key: f.key, label: f.label, value: displayValue(f, data[f.key]), wide: f.type === 'textarea' }))
  for (const key of Object.keys(data).filter((k) => !known.has(k))) {
    rows.push({ key, label: key, value: String(data[key]), wide: false })
  }
  return rows
})
</script>

<template>
  <dl v-if="rows.length" class="grid grid-cols-1 gap-x-6 gap-y-2 text-sm md:grid-cols-2">
    <div v-for="r in rows" :key="r.key" :class="r.wide ? 'md:col-span-2' : ''">
      <dt class="muted text-xs">{{ r.label }}</dt>
      <dd class="whitespace-pre-wrap break-words">{{ r.value }}</dd>
    </div>
  </dl>
</template>
