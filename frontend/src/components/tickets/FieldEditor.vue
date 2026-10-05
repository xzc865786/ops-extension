<script setup lang="ts">
// Edits one field of a category in place. System fields keep their key, type, required flag,
// option values and display condition; the backend rejects any change to those anyway.
import { computed, ref } from 'vue'
import { FIELD_TYPES, fieldTypeLabel, type FieldType, type FormField } from '@/utils/ticketForm'

const props = defineProps<{
  field: FormField
  earlier: FormField[]
  first: boolean
  last: boolean
  startOpen?: boolean
}>()
const emit = defineEmits<{ up: []; down: []; remove: [] }>()

const open = ref(!!props.startOpen)
const f = props.field
const locked = computed(() => !!f.system)
const hasOptions = computed(() => f.type === 'select' || f.type === 'radio')
const isText = computed(() => f.type === 'text' || f.type === 'textarea')
const isNumber = computed(() => f.type === 'number' || f.type === 'money')
const conditionSources = computed(() => props.earlier.filter((g) => ['select', 'radio', 'confirm'].includes(g.type)))
const conditionSource = computed(() => props.earlier.find((g) => g.key === f.show_if?.field))

function changeType(type: FieldType) {
  f.type = type
  if (type === 'select' || type === 'radio') {
    if (!f.options?.length) f.options = [{ value: 'OPTION_1', label: '选项 1' }]
  } else {
    f.options = []
  }
  if (type !== 'text' && type !== 'textarea') f.max_length = null
  if (type !== 'number' && type !== 'money') f.min = f.max = null
}

function addOption() {
  const options = (f.options ||= [])
  let n = options.length + 1
  while (options.some((o) => o.value === `OPTION_${n}`)) n += 1
  options.push({ value: `OPTION_${n}`, label: `选项 ${n}` })
}

function moveOption(index: number, delta: number) {
  const options = f.options!
  const [item] = options.splice(index, 1)
  options.splice(index + delta, 0, item)
}

function setConditionField(key: string) {
  if (!key) {
    f.show_if = null
    return
  }
  const source = props.earlier.find((g) => g.key === key)
  f.show_if = source?.type === 'confirm' ? { field: key, equals: true } : { field: key, in: [] }
}

function toggleConditionValue(value: string, checked: boolean) {
  const cond = f.show_if!
  const values = new Set(cond.in ?? (typeof cond.equals === 'string' ? [cond.equals] : []))
  if (checked) values.add(value)
  else values.delete(value)
  const list = [...values]
  f.show_if = list.length === 1 ? { field: cond.field, equals: list[0] } : { field: cond.field, in: list }
}

const conditionValues = computed(() => {
  const cond = f.show_if
  if (!cond) return []
  return cond.in ?? (typeof cond.equals === 'string' ? [cond.equals] : [])
})

function numberOrNull(value: string) {
  return value === '' ? null : Number(value)
}
</script>

<template>
  <div class="rounded-xl border border-gray-200 dark:border-dark-600">
    <div class="flex flex-wrap items-center gap-2 px-3 py-2">
      <button type="button" class="min-w-0 flex-1 text-left" @click="open = !open">
        <span class="text-sm font-medium">{{ f.label || '（未命名）' }}</span>
        <span class="muted ml-2 text-xs">{{ fieldTypeLabel(f.type) }} · {{ f.key }}</span>
        <span v-if="f.required" class="badge-warning ml-2">必填</span>
        <span v-if="f.system" class="badge-gray ml-1">系统字段</span>
        <span v-if="f.show_if" class="badge-primary ml-1">有显示条件</span>
      </button>
      <button type="button" class="btn-ghost btn-sm" :disabled="first" aria-label="上移" @click="emit('up')">↑</button>
      <button type="button" class="btn-ghost btn-sm" :disabled="last" aria-label="下移" @click="emit('down')">↓</button>
      <button type="button" class="btn-ghost btn-sm text-red-600" :disabled="locked" :title="locked ? '系统字段不能删除' : ''" @click="emit('remove')">删除</button>
      <button type="button" class="btn-ghost btn-sm" @click="open = !open">{{ open ? '收起' : '编辑' }}</button>
    </div>

    <div v-if="open" class="space-y-4 border-t border-gray-200 p-3 dark:border-dark-600">
      <div class="grid gap-3 sm:grid-cols-3">
        <div>
          <label class="input-label">名称</label>
          <input v-model="f.label" class="input" maxlength="60" />
        </div>
        <div>
          <label class="input-label">字段标识</label>
          <input v-model.trim="f.key" class="input font-mono" maxlength="40" :disabled="locked" />
        </div>
        <div>
          <label class="input-label">类型</label>
          <select class="input" :value="f.type" :disabled="locked" @change="changeType(($event.target as HTMLSelectElement).value as FieldType)">
            <option v-for="t in FIELD_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </div>
      </div>
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label class="input-label">提示文字（显示在输入框下方）</label>
          <input v-model="f.help" class="input" maxlength="200" />
        </div>
        <div>
          <label class="input-label">占位文字</label>
          <input v-model="f.placeholder" class="input" maxlength="100" />
        </div>
      </div>
      <div class="flex flex-wrap items-end gap-4">
        <label class="flex items-center gap-2 text-sm">
          <input v-model="f.required" type="checkbox" :disabled="locked" /> 必填
        </label>
        <div v-if="isText" class="w-36">
          <label class="input-label">长度上限</label>
          <input class="input" type="number" min="1" :max="f.type === 'textarea' ? 5000 : 500"
                 :value="f.max_length ?? ''" @input="f.max_length = numberOrNull(($event.target as HTMLInputElement).value)" />
        </div>
        <template v-if="isNumber">
          <div class="w-32">
            <label class="input-label">最小值</label>
            <input class="input" type="number" :value="f.min ?? ''" @input="f.min = numberOrNull(($event.target as HTMLInputElement).value)" />
          </div>
          <div class="w-32">
            <label class="input-label">最大值</label>
            <input class="input" type="number" :value="f.max ?? ''" @input="f.max = numberOrNull(($event.target as HTMLInputElement).value)" />
          </div>
        </template>
      </div>

      <div v-if="hasOptions">
        <p class="input-label">选项</p>
        <div class="space-y-2">
          <div v-for="(o, i) in f.options" :key="i" class="flex flex-wrap items-center gap-2">
            <input v-model.trim="o.value" class="input w-40 font-mono" maxlength="40" placeholder="选项值" :disabled="locked" />
            <input v-model="o.label" class="input min-w-[8rem] flex-1" maxlength="60" placeholder="显示名称" />
            <button type="button" class="btn-ghost btn-sm" :disabled="locked || i === 0" @click="moveOption(i, -1)">↑</button>
            <button type="button" class="btn-ghost btn-sm" :disabled="locked || i === f.options!.length - 1" @click="moveOption(i, 1)">↓</button>
            <button type="button" class="btn-ghost btn-sm text-red-600" :disabled="locked || f.options!.length <= 1" @click="f.options!.splice(i, 1)">删除</button>
          </div>
        </div>
        <button v-if="!locked" type="button" class="btn-secondary btn-sm mt-2" @click="addOption">添加选项</button>
        <p class="muted mt-1 text-xs">选项值保存在工单里，已有工单使用后不建议修改；只改显示名称不影响已有工单。</p>
      </div>

      <div>
        <p class="input-label">显示条件</p>
        <div class="flex flex-wrap items-center gap-3 text-sm">
          <select class="input w-56" :value="f.show_if?.field || ''" :disabled="locked"
                  @change="setConditionField(($event.target as HTMLSelectElement).value)">
            <option value="">总是显示</option>
            <option v-for="g in conditionSources" :key="g.key" :value="g.key">当「{{ g.label }}」…</option>
          </select>
          <template v-if="f.show_if && conditionSource">
            <select v-if="conditionSource.type === 'confirm'" v-model="f.show_if.equals" class="input w-36" :disabled="locked">
              <option :value="true">已勾选</option>
              <option :value="false">未勾选</option>
            </select>
            <template v-else>
              <span class="muted">选择以下任一项时显示：</span>
              <label v-for="o in conditionSource.options" :key="o.value" class="flex items-center gap-1">
                <input type="checkbox" :disabled="locked" :checked="conditionValues.includes(o.value)"
                       @change="toggleConditionValue(o.value, ($event.target as HTMLInputElement).checked)" />
                {{ o.label }}
              </label>
            </template>
          </template>
        </div>
        <p v-if="!conditionSources.length && !f.show_if" class="muted mt-1 text-xs">只能根据排在前面的下拉、单选或勾选字段设置条件。</p>
      </div>
    </div>
  </div>
</template>
