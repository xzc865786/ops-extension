<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useTemplateRef } from 'vue'
import { VueDatePicker } from '@vuepic/vue-datepicker'
import '@vuepic/vue-datepicker/dist/main.css'
import { zhCN } from 'date-fns/locale'
import { RANGE_PRESETS, isDateRange, presetFor, toDateString, type DateRange, type RangePreset } from '@/utils/dateRange'

// The picker works in Date objects; `model-type` is avoided because the library routes it through
// the function formatter below. Strings are parsed as local dates, not UTC.
const toDate = (value: string) => {
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d)
}

const props = withDefaults(defineProps<{
  modelValue: DateRange
  /** Longest selectable span in days, kept in line with the backend limit. */
  maxDays?: number
  ariaLabel?: string
}>(), { maxDays: 1096, ariaLabel: '日期区间' })

const emit = defineEmits<{ 'update:modelValue': [value: DateRange] }>()

const pickerValue = computed(() => props.modelValue.map(toDate))
const activePreset = computed(() => presetFor(props.modelValue))

// Two side-by-side months only when there is room; the stacked mobile menu gets one.
const wide = window.matchMedia('(min-width: 768px)')
const isWide = ref(wide.matches)
const onWideChange = (e: MediaQueryListEvent) => { isWide.value = e.matches }
wide.addEventListener('change', onWideChange)
onBeforeUnmount(() => wide.removeEventListener('change', onWideChange))

function formatRange(dates: Date | Date[]) {
  return ([] as Date[]).concat(dates).filter(Boolean).map(toDateString).join(' ~ ')
}

// Presets are our own sidebar buttons rather than the built-in `preset-dates`: without auto-apply
// (which breaks two-click range selection in this library) built-in presets would need a second
// click on 确定, whereas a preset is a complete range and can apply at once.
const picker = useTemplateRef<InstanceType<typeof VueDatePicker>>('picker')

function applyPreset(preset: RangePreset) {
  emit('update:modelValue', preset.range())
  picker.value?.closeMenu()
}

function onUpdate(value: Date[] | null) {
  // Partial or cleared selections are ignored so the report never queries an open range.
  const range = value?.every((d) => d instanceof Date) ? value.map(toDateString) : null
  if (isDateRange(range)) emit('update:modelValue', range)
}
</script>

<template>
  <div class="date-range-picker">
    <VueDatePicker
      ref="picker"
      :model-value="pickerValue"
      :range="{ maxRange: maxDays }"
      :multi-calendars="isWide ? 2 : false"
      :locale="zhCN"
      :week-start="1"
      :formats="{ input: formatRange, preview: formatRange }"
      :time-config="{ enableTimePicker: false }"
      :input-attrs="{ clearable: false }"
      :action-row="{ selectBtnLabel: '确定', cancelBtnLabel: '取消', showNow: false }"
      :aria-labels="{ input: ariaLabel }"
      @update:model-value="onUpdate"
    >
      <template #left-sidebar>
        <div class="date-range-presets">
          <button
            v-for="preset in RANGE_PRESETS"
            :key="preset.key"
            type="button"
            class="date-range-preset"
            :class="{ 'date-range-preset-active': activePreset?.key === preset.key }"
            @click="applyPreset(preset)"
          >{{ preset.label }}</button>
        </div>
      </template>
    </VueDatePicker>
    <span v-if="activePreset" class="date-range-tag">{{ activePreset.label }}</span>
  </div>
</template>
