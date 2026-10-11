export function beijingToday(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  const get = (type: string) => parts.find(p => p.type === type)!.value
  return `${get('year')}-${get('month')}-${get('day')}`
}
export function cents(value: string): bigint {
  if (!/^\d{1,16}(\.\d{1,2})?$/.test(value)) throw new Error('金额须为正数，最多两位小数')
  const [whole, fraction = ''] = value.split('.')
  const result = BigInt(whole!) * 100n + BigInt(fraction.padEnd(2, '0'))
  if (result <= 0n || result > 999999999999999999n) throw new Error('金额超出可填写范围')
  return result
}
export function money(value: bigint): string {
  const negative = value < 0n, absolute = negative ? -value : value
  return `${negative ? '-' : ''}${absolute / 100n}.${(absolute % 100n).toString().padStart(2, '0')}`
}
export function totalMoney(values: string[]): string { return money(values.reduce((sum, v) => sum + cents(v), 0n)) }
export function convert(amount: string, rate: string): string {
  if (!/^\d+(\.\d{1,12})?$/.test(rate)) throw new Error('参考汇率无效')
  const [whole, fraction = ''] = rate.split('.')
  const numerator = BigInt(whole! + fraction)
  if (numerator <= 0n) throw new Error('参考汇率无效')
  const divisor = 10n ** BigInt(fraction.length), product = cents(amount) * numerator
  return money((product + divisor / 2n) / divisor)
}
export interface Quote { id: string; rate: string; effective_date: string; fetched_at: string; source: string }
export interface ConversionState {
  currency: 'CNY' | 'USD'; amount: string; rmb_amount: string; amount_mode: 'AUTO' | 'MANUAL'
  quote: Quote | null; pendingDecision: boolean; loading: boolean; error: string
}
export function conversionController(state: ConversionState, fetchQuote: (refresh: boolean) => Promise<Quote>) {
  let generation = 0
  function invalidate() { generation++; state.loading = false }
  function calculate() { try { if (state.quote) state.rmb_amount = convert(state.amount, state.quote.rate) } catch { state.rmb_amount = '' } }
  async function refresh(force = true) {
    const current = ++generation
    if (state.currency !== 'USD') return
    state.loading = true; state.error = ''; state.amount_mode = 'AUTO'; state.pendingDecision = false; state.rmb_amount = ''; state.quote = null
    try {
      const quote = await fetchQuote(force)
      if (current !== generation || state.currency !== 'USD' || (state.amount_mode as string) === 'MANUAL') return
      state.quote = quote; calculate()
    } catch { if (current === generation) state.error = '参考汇率获取失败，可重试或直接填写人民币金额' }
    finally { if (current === generation) state.loading = false }
  }
  function setAmount(value: string) {
    if (value === state.amount) return
    const wasLoading = state.loading
    invalidate(); state.amount = value
    if (state.currency === 'CNY') { state.rmb_amount = value; return }
    if (state.amount_mode === 'MANUAL') { state.pendingDecision = true; return }
    if (state.quote) calculate()
    else if (wasLoading || value) void refresh(false)
  }
  function setRmb(value: string) { invalidate(); state.rmb_amount = value; state.amount_mode = 'MANUAL'; state.pendingDecision = false }
  function setCurrency(value: 'CNY' | 'USD') {
    invalidate(); state.currency = value; state.quote = null; state.error = ''; state.amount_mode = 'AUTO'; state.pendingDecision = false
    state.rmb_amount = value === 'CNY' ? state.amount : ''
    if (value === 'USD') void refresh(false)
  }
  function keepManual() { state.pendingDecision = false }
  return { setAmount, setRmb, setCurrency, refresh, keepManual, dispose: invalidate }
}
