import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('../../src/utils/dateRange.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
const { RANGE_PRESETS, beijingCalendarDate, dateRangeParams } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'))
test('date presets handle Beijing midnight, leap years and previous quarters across years', () => {
  const today = beijingCalendarDate(new Date('2025-12-31T16:01:00Z'))
  const preset = key => RANGE_PRESETS.find(p => p.key === key)
  assert.deepEqual(preset('this-month').range(today), ['2026-01-01', '2026-01-31'])
  assert.deepEqual(preset('last-month').range(today), ['2025-12-01', '2025-12-31'])
  assert.deepEqual(preset('last-quarter').range(today), ['2025-10-01', '2025-12-31'])
  assert.deepEqual(preset('this-month').range(new Date(2024, 1, 20)), ['2024-02-01', '2024-02-29'])
})
test('custom and unrestricted dates use the same compatible query for list, report and export', () => {
  assert.deepEqual(dateRangeParams(['2025-12-31', '2026-01-01']), { month: '', date_from: '2025-12-31', date_to: '2026-01-01' })
  assert.deepEqual(dateRangeParams(null), { month: '', date_from: undefined, date_to: undefined })
})
