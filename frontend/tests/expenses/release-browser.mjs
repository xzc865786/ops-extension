// Built-artifact regression: static release switches, iframe navigation and missing chunks.
// Only synthetic GET responses are served; any API write makes the test fail.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFileSync, existsSync, mkdirSync } from 'node:fs'
import { resolve, sep, dirname } from 'node:path'
import { createRequire } from 'node:module'
const { chromium } = createRequire(import.meta.url)('playwright')
const current = resolve('dist'), previous = process.env.OPS_RELEASE_PREVIOUS_DIST
assert.ok(existsSync(resolve(current, 'index.html')), 'Run npm run build first')
let version = 'current', preserve = false, blocked = null, writes = 0
const requests = []
const record = { id: 99001, title: '加载验收记录', expense_date: '2026-10-11', category: 'OTHER', category_label: '其他', payer: '验收付款人', merchant: '', currency: 'CNY', amount: '20.00', rmb_amount: '20.00', amount_mode: 'AUTO', needs_reimbursement: false, active: true, status: 'NOT_REQUIRED', version: 1, notes: '', attachments: [], reimbursements: [], events: [] }
const legacy = { id: 99002, claim_no: 'E-CACHE-TEST', expense_date: '2026-10-11', category: 'OTHER', currency: 'CNY', amount_tax_included: '20.00', pay_type: 'PERSONAL_ADVANCE', status: 'PAID', description: '旧单加载验收', remaining_amount: '0', items: [], payments: [], attachments: [], events: [] }
const meta = { categories: [{ value: 'CLOUD_SERVER', label: '云服务器' }, { value: 'OTHER', label: '其他' }], payers: [], merchants: [], pay_types: [], currencies: ['CNY', 'USD'] }
const server = createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname
  const send = (status, type, body) => {
    requests.push({ path, status, type })
    const cache = version === 'previous' && type === 'text/html' && path.startsWith('/ext/app/') ? 'public, max-age=3600' : 'no-store'
    res.writeHead(status, { 'Content-Type': type, 'Cache-Control': cache }); res.end(body)
  }
  if (path.startsWith('/ext/api/')) {
    if (req.method !== 'GET') { writes++; return send(405, 'application/json', '{}') }
    let data
    if (path.endsWith('/auth/me')) data = { id: 1, sub2api_user_id: 1, username: '验收管理员', sub2api_role: 'admin' }
    else if (path.endsWith('/meta')) data = meta
    else if (path.endsWith('/expense-records/99001')) data = record
    else if (path.endsWith('/expense-records')) data = { items: [record], total: 1, unconfirmed_count: 0 }
    else if (path.endsWith('/expenses/99002')) data = legacy
    else if (path.endsWith('/expenses')) data = { items: [legacy] }
    else if (/\/(cost-centers|suppliers|payment-accounts)$/.test(path)) data = []
    else return send(404, 'application/json', '{}')
    return send(200, 'application/json', JSON.stringify(data))
  }
  if (path === '/test-frame') return send(200, 'text/html', '<iframe title="Ops" src="/ext/app/admin/expenses" style="width:100%;height:850px;border:0"></iframe>')
  if (path === '/test-frame-fresh') return send(200, 'text/html', `<iframe title="Ops" src="/ext/app/admin/expenses?_ops_entry=entry-${requests.length}" style="width:100%;height:850px;border:0"></iframe>`)
  const root = version === 'previous' ? resolve(previous) : current
  const relative = path.replace(/^\/ext\/app\//, '')
  const candidates = [resolve(root, relative)]
  if (preserve && previous && path.startsWith('/ext/app/assets/')) candidates.push(resolve(previous, relative))
  if (blocked?.test(path)) return send(404, 'text/plain', 'Not found')
  for (const file of candidates) {
    if (file.startsWith(root + sep) || (previous && file.startsWith(resolve(previous) + sep))) {
      if (existsSync(file) && /\.(js|css)$/.test(file)) return send(200, file.endsWith('.js') ? 'application/javascript' : 'text/css', readFileSync(file))
    }
  }
  // Match the former production bug for the reproduction phase only.
  if (path.startsWith('/ext/app/assets/') && preserve) return send(404, 'text/plain', 'Not found')
  return send(200, 'text/html', readFileSync(resolve(root, 'index.html')))
})
await new Promise(done => server.listen(0, '127.0.0.1', done))
const base = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.OPS_BROWSER_EXECUTABLE || undefined })
const context = () => browser.newContext({ viewport: { width: 1280, height: 900 } })
try {
  if (previous) {
    version = 'previous'; preserve = false
    const ctx = await context(), page = await ctx.newPage()
    await page.goto(base + '/test-frame')
    const frame = page.frameLocator('iframe')
    await frame.getByRole('link', { name: '新建报账', exact: true }).waitFor()
    version = 'current'
    const failedResponse = page.waitForResponse(r => /ExpenseForm-.*\.js$/.test(r.url()))
    await frame.getByRole('link', { name: '新建报账', exact: true }).click()
    await failedResponse
    assert.ok(requests.some(r => /ExpenseForm-.*\.js$/.test(r.path) && r.type === 'text/html'))
    assert.equal(await frame.getByRole('heading', { name: '报账管理', exact: true }).isVisible(), true)
    await ctx.close()
    console.log('Reproduced: stale iframe cannot navigate when a removed JS chunk receives HTML.')

    version = 'previous'; preserve = true
    const oldCtx = await context(), oldPage = await oldCtx.newPage()
    const errors = []; oldPage.on('pageerror', e => errors.push(e.message))
    await oldPage.goto(base + '/test-frame')
    const oldFrame = oldPage.frameLocator('iframe')
    await oldFrame.getByRole('link', { name: '新建报账', exact: true }).waitFor()
    version = 'current'
    await oldFrame.getByRole('link', { name: '新建报账', exact: true }).click()
    await oldFrame.getByRole('heading', { name: '新建报账', exact: true }).waitFor()
    await oldFrame.getByRole('link', { name: /返回/ }).click()
    await oldFrame.getByRole('link', { name: 'E-CACHE-TEST', exact: true }).click()
    await oldFrame.getByRole('heading', { name: 'E-CACHE-TEST', exact: true }).waitFor()
    assert.deepEqual(errors, [])
    await oldCtx.close()
    console.log('Passed: an already-open old iframe can open new/detail routes with retained original chunks.')

    version = 'previous'
    const cachedCtx = await context(), cached = await cachedCtx.newPage()
    await cached.goto(base + '/test-frame')
    const cachedFrame = cached.frameLocator('iframe')
    await cachedFrame.getByRole('heading', { name: '报账管理', exact: true }).waitFor()
    version = 'current'
    await cached.goto(base + '/test-frame?return=1')
    await cachedFrame.getByRole('heading', { name: '报账管理', exact: true }).waitFor()
    await cached.goto(base + '/test-frame-fresh')
    await cachedFrame.getByRole('heading', { name: '支出记录', exact: true }).waitFor()
    await cachedFrame.getByRole('link', { name: '记一笔', exact: true }).click()
    await cachedFrame.getByRole('button', { name: '保存支出', exact: true }).waitFor()
    assert.equal(await cachedFrame.getByRole('button', { name: '保存草稿', exact: true }).count(), 0)
    await cachedCtx.close()
    console.log('Passed: unchanged iframe URL reuses cached old HTML; a fresh entry query loads the current create form.')
  }

  version = 'current'; preserve = true
  const freshCtx = await context(), fresh = await freshCtx.newPage()
  const errors = []; fresh.on('pageerror', e => errors.push(e.message))
  await fresh.goto(base + '/test-frame')
  const frame = fresh.frameLocator('iframe')
  await frame.getByRole('link', { name: '记一笔', exact: true }).click()
  await frame.locator('#expense-title').waitFor()
  if (process.env.OPS_RELEASE_SCREENSHOT) {
    mkdirSync(dirname(resolve(process.env.OPS_RELEASE_SCREENSHOT)), { recursive: true })
    await fresh.screenshot({ path: resolve(process.env.OPS_RELEASE_SCREENSHOT), fullPage: true })
  }
  await frame.getByRole('link', { name: /返回支出记录/ }).click()
  await frame.getByRole('link', { name: '详情', exact: true }).click()
  await frame.getByRole('heading', { name: record.title, exact: true }).waitFor()
  assert.deepEqual(errors, [])
  await freshCtx.close()
  console.log('Passed: current built Vue iframe opens both create and detail pages without errors.')

  const retryCtx = await context(), retry = await retryCtx.newPage()
  await retry.goto(base + '/test-frame')
  const retryFrame = retry.frameLocator('iframe')
  await retryFrame.getByRole('link', { name: '记一笔', exact: true }).waitFor()
  blocked = /ExpenseForm-.*\.js$/
  await retryFrame.getByRole('link', { name: '记一笔', exact: true }).click()
  await retryFrame.getByRole('alert').getByText(/页面已更新或网络连接中断/).waitFor()
  blocked = null
  await retryFrame.getByRole('button', { name: '刷新页面', exact: true }).click()
  await retryFrame.getByRole('link', { name: '记一笔', exact: true }).click()
  await retryFrame.locator('#expense-title').waitFor()
  await retryCtx.close()
  console.log('Passed: a missing chunk shows a notice; explicit refresh restores iframe navigation.')

  const formCtx = await context(), form = await formCtx.newPage()
  await form.goto(base + '/ext/app/admin/expenses/new')
  await form.locator('#expense-title').fill('未保存的购买说明')
  blocked = /ReportDashboard-.*\.js$/
  await form.getByRole('link', { name: '月度开支', exact: true }).click()
  await form.getByRole('alert').getByText(/先记录未保存的内容/).waitFor()
  assert.equal(await form.locator('#expense-title').inputValue(), '未保存的购买说明')
  assert.equal(new URL(form.url()).pathname, '/ext/app/admin/expenses/new')
  assert.equal(writes, 0)
  await formCtx.close()
  console.log('Passed: failure keeps unsaved form content; no automatic reload and no API writes.')
} finally {
  await browser.close()
  await new Promise(done => server.close(done))
}
