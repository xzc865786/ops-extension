<script setup lang="ts">
// Renders a category's configured fields. `values` is a reactive object owned by the parent and edited in place.
import { computed } from 'vue'
import { MAX_ORDER_NOS, isVisible, type FormField } from '@/utils/ticketForm'

const props = defineProps<{
  fields: FormField[]
  values: Record<string, any>
  errors?: Record<string, string>
  idPrefix?: string
}>()

const visible = computed(() => props.fields.filter((f) => isVisible(f, props.values)))
const id = (f: FormField) => `${props.idPrefix || 'ff'}-${f.key}`
const wide = (f: FormField) => ['textarea', 'order_no_list', 'confirm', 'radio'].includes(f.type)
</script>

<template>
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    <div v-for="f in visible" :key="f.key" :class="wide(f) ? 'sm:col-span-2' : ''">
      <label v-if="f.type === 'confirm'" class="flex items-start gap-2 text-sm">
        <input :id="id(f)" v-model="values[f.key]" type="checkbox" class="mt-0.5" />
        <span>{{ f.label }}<span v-if="f.required" class="text-red-500"> *</span></span>
      </label>
      <template v-else>
        <label class="input-label" :for="id(f)">
          {{ f.label }}<span v-if="f.required" class="text-red-500"> *</span>
        </label>
        <textarea
          v-if="f.type === 'textarea'"
          :id="id(f)"
          v-model="values[f.key]"
          rows="3"
          class="input"
          :maxlength="f.max_length || undefined"
          :placeholder="f.placeholder"
        />
        <textarea
          v-else-if="f.type === 'order_no_list'"
          :id="id(f)"
          v-model="values[f.key]"
          rows="2"
          class="input font-mono"
          :placeholder="f.placeholder || `每行一个，最多 ${MAX_ORDER_NOS} 个`"
        />
        <select v-else-if="f.type === 'select'" :id="id(f)" v-model="values[f.key]" class="input">
          <option value="">请选择</option>
          <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <div v-else-if="f.type === 'radio'" :id="id(f)" class="flex flex-wrap gap-x-5 gap-y-2 text-sm">
          <label v-for="o in f.options" :key="o.value" class="flex items-center gap-2">
            <input v-model="values[f.key]" type="radio" :name="id(f)" :value="o.value" /> {{ o.label }}
          </label>
        </div>
        <input
          v-else-if="f.type === 'number' || f.type === 'money'"
          :id="id(f)"
          v-model="values[f.key]"
          type="text"
          :inputmode="f.type === 'money' ? 'decimal' : 'numeric'"
          class="input"
          :placeholder="f.placeholder || (f.type === 'money' ? '0.00' : '')"
        />
        <input v-else-if="f.type === 'date'" :id="id(f)" v-model="values[f.key]" type="date" class="input" />
        <input v-else-if="f.type === 'datetime'" :id="id(f)" v-model="values[f.key]" type="datetime-local" class="input" />
        <input
          v-else
          :id="id(f)"
          v-model="values[f.key]"
          :type="f.type === 'email' ? 'email' : 'text'"
          class="input"
          :class="f.type === 'order_no' ? 'font-mono' : ''"
          :maxlength="f.max_length || undefined"
          :placeholder="f.placeholder"
        />
      </template>
      <p v-if="errors?.[f.key]" class="mt-1 text-xs text-red-600">{{ errors[f.key] }}</p>
      <p v-else-if="f.help" class="muted mt-1 text-xs">{{ f.help }}</p>
    </div>
  </div>
</template>
