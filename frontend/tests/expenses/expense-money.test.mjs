import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('../../src/utils/expenseMoney.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
const { beijingToday, cents, convert, totalMoney, conversionController, yuan, signedCents } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'))
const quote = rate => ({ id: 'quote-'+rate, rate, effective_date: '2026-10-09', fetched_at: '2026-10-11T00:00:00Z', source: 'test' })
const state = () => ({ currency: 'USD', amount: '20', rmb_amount: '', amount_mode: 'AUTO', quote: null, pendingDecision: false, loading: false, error: '' })
function pending() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b }); return {promise, resolve, reject} }
test('Beijing midnight and month boundary use Shanghai date', () => {
  assert.equal(beijingToday(new Date('2026-09-30T16:01:00Z')), '2026-10-01')
  assert.equal(beijingToday(new Date('2026-10-11T16:00:00Z')), '2026-10-12')
})
test('decimal conversion and large sums do not use floating point', () => {
  assert.equal(convert('20','7.10'), '142.00'); assert.equal(convert('1','7.105'), '7.11')
  assert.equal(totalMoney(['0.1','0.1','0.1']), '0.30')
  assert.equal(convert('9999999999999999.99','1.000000000000'), '9999999999999999.99')
  for (const value of ['0','-1','NaN','Infinity','1e3','1.001']) assert.throws(() => cents(value))
})
test('manual amount survives a slow response', async () => {
  const s=state(), wait=pending(), control=conversionController(s, () => wait.promise)
  const request=control.refresh(); control.setRmb('143.26'); wait.resolve(quote('7.10')); await request
  assert.equal(s.rmb_amount,'143.26'); assert.equal(s.amount_mode,'MANUAL'); assert.equal(s.quote,null)
})
test('currency changes invalidate old quote and reset all rate state', async () => {
  const s=state(), wait=pending(), control=conversionController(s, () => wait.promise)
  const request=control.refresh(); control.setCurrency('CNY'); wait.resolve(quote('7.10')); await request
  assert.equal(s.rmb_amount,'20'); assert.equal(s.quote,null); assert.equal(s.amount_mode,'AUTO')
})
test('new amount request wins even when old request arrives last', async () => {
  const s=state(), first=pending(), second=pending(); let count=0
  const control=conversionController(s, () => ++count === 1 ? first.promise : second.promise)
  const old=control.refresh(); control.setAmount('30'); second.resolve(quote('7.20')); await second.promise; await Promise.resolve()
  first.resolve(quote('7.10')); await old
  assert.equal(s.rmb_amount,'216.00'); assert.equal(s.quote.rate,'7.20')
})
test('manual original amount changes require a decision and retain reference snapshot', async () => {
  const s=state(), control=conversionController(s, async () => quote('7.10')); await control.refresh()
  control.setRmb('143.26'); control.setAmount('25')
  assert.equal(s.pendingDecision,true); assert.equal(s.rmb_amount,'143.26'); assert.equal(s.quote.rate,'7.10')
  control.keepManual(); assert.equal(s.pendingDecision,false)
  await control.refresh(true); assert.equal(s.rmb_amount,'177.50'); assert.equal(s.amount_mode,'AUTO')
})
test('editing initialization never fetches or revalues', () => {
  const s={...state(),rmb_amount:'143.26',amount_mode:'MANUAL',quote:quote('7.10')}; let requests=0
  conversionController(s, async () => { requests++; return quote('8') })
  assert.equal(requests,0); assert.equal(s.rmb_amount,'143.26')
})
test('offline still permits manual value and explicit refresh clears fake rates', async () => {
  const s=state(), control=conversionController(s, async () => { throw new Error('offline') })
  await control.refresh(); assert.ok(s.error); assert.equal(s.quote,null)
  control.setRmb('143.26'); assert.equal(s.rmb_amount,'143.26'); assert.equal(s.amount_mode,'MANUAL')
})
test('display amounts group thousands and report sums accept zero and negatives', () => {
  assert.equal(yuan('1234567.5'), '¥ 1,234,567.50'); assert.equal(yuan('-1.00'), '-¥ 1.00'); assert.equal(yuan('999'), '¥ 999.00'); assert.equal(yuan(null), '—')
  assert.equal(signedCents('0.00'), 0n); assert.equal(signedCents('-1.5'), -150n); assert.throws(() => signedCents('1e3'))
})
