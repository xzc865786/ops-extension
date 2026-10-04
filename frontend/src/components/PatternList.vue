<script setup lang="ts">
import { ref } from 'vue'
import { PATTERN_RE } from '@/utils/manualRules'

// Ordered list of model IDs / wildcard patterns; order matters for recommendations.
const props = withDefaults(defineProps<{ modelValue: string[]; placeholder?: string; ordered?: boolean }>(), {
  placeholder: '例如 gpt-6.1-sol 或 claude-sonnet-*',
  ordered: false,
})
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const draft = ref('')
const error = ref('')

function update(list: string[]) {
  emit('update:modelValue', list)
}

function add() {
  const value = draft.value.trim()
  error.value = ''
  if (!value) return
  if (!PATTERN_RE.test(value) || !/[A-Za-z0-9]/.test(value)) {
    error.value = '只能用字母、数字和 . _ : / - *'
    return
  }
  if (props.modelValue.includes(value)) {
    error.value = '已经在列表里了'
    return
  }
  update([...props.modelValue, value])
  draft.value = ''
}

function remove(index: number) {
  update(props.modelValue.filter((_, i) => i !== index))
}

function move(index: number, delta: number) {
  const list = [...props.modelValue]
  const target = index + delta
  if (target < 0 || target >= list.length) return
  ;[list[index], list[target]] = [list[target], list[index]]
  update(list)
}
</script>

<template>
  <div class="space-y-2">
    <ol v-if="modelValue.length" class="space-y-1">
      <li v-for="(item, index) in modelValue" :key="item" class="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm">
        <span v-if="ordered" class="w-5 text-xs text-slate-400">{{ index + 1 }}</span>
        <code class="flex-1 truncate">{{ item }}</code>
        <template v-if="ordered">
          <button type="button" class="btn-ghost btn-sm" :disabled="index === 0" aria-label="上移" @click="move(index, -1)">↑</button>
          <button type="button" class="btn-ghost btn-sm" :disabled="index === modelValue.length - 1" aria-label="下移" @click="move(index, 1)">↓</button>
        </template>
        <button type="button" class="btn-ghost btn-sm text-red-600" aria-label="删除" @click="remove(index)">删除</button>
      </li>
    </ol>
    <p v-else class="muted text-sm">（空）</p>
    <div class="flex gap-2">
      <input v-model="draft" class="input" :placeholder="placeholder" @keydown.enter.prevent="add" />
      <button type="button" class="btn-secondary btn-sm shrink-0" @click="add">添加</button>
    </div>
    <p v-if="error" class="text-xs text-red-600">{{ error }}</p>
  </div>
</template>
