/** Inclusive date range as local `YYYY-MM-DD` strings (never via toISOString, which shifts to UTC). */
export type DateRange = [string, string]

export interface RangePreset {
  key: string
  label: string
  range: (today?: Date) => DateRange
}

export function toDateString(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// Day 0 of the next month is the last day of this one; Date handles month/year overflow.
function months(year: number, startMonth: number, count: number): DateRange {
  return [toDateString(new Date(year, startMonth, 1)), toDateString(new Date(year, startMonth + count, 0))]
}

const quarterStart = (d: Date) => Math.floor(d.getMonth() / 3) * 3

export function beijingCalendarDate(now = new Date()): Date {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  const get = (type: string) => Number(parts.find(p => p.type === type)!.value)
  return new Date(get('year'), get('month') - 1, get('day'))
}

export function dateRangeParams(range: DateRange | null) {
  return { month: '', date_from: range?.[0], date_to: range?.[1] }
}

export function dateRangeLabel(range: DateRange | null): string {
  return range ? `${range[0]} ~ ${range[1]}` : '不限日期'
}

export const RANGE_PRESETS: RangePreset[] = [
  { key: 'this-month', label: '本月', range: (t = beijingCalendarDate()) => months(t.getFullYear(), t.getMonth(), 1) },
  { key: 'last-month', label: '上月', range: (t = beijingCalendarDate()) => months(t.getFullYear(), t.getMonth() - 1, 1) },
  { key: 'this-quarter', label: '本季度', range: (t = beijingCalendarDate()) => months(t.getFullYear(), quarterStart(t), 3) },
  { key: 'last-quarter', label: '上季度', range: (t = beijingCalendarDate()) => months(t.getFullYear(), quarterStart(t) - 3, 3) },
  { key: 'this-year', label: '本年', range: (t = beijingCalendarDate()) => months(t.getFullYear(), 0, 12) },
  { key: 'last-year', label: '上年', range: (t = beijingCalendarDate()) => months(t.getFullYear() - 1, 0, 12) },
  { key: 'last-12-months', label: '近 12 个月', range: (t = beijingCalendarDate()) => months(t.getFullYear(), t.getMonth() - 11, 12) },
]

export function presetFor(range: DateRange | null | undefined): RangePreset | undefined {
  if (!range) return undefined
  return RANGE_PRESETS.find((p) => {
    const [start, end] = p.range()
    return start === range[0] && end === range[1]
  })
}

export function isDateRange(value: unknown): value is DateRange {
  return Array.isArray(value) && value.length === 2
    && value.every((v) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v))
    && value[0] <= value[1]
}
