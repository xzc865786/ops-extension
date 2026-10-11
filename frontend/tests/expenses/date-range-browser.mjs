// Built Vue iframe test with synthetic GET responses; no production credentials or writes.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFileSync, existsSync, mkdirSync } from 'node:fs'
import { resolve, sep } from 'node:path'
import { createRequire } from 'node:module'
const { chromium } = createRequire(import.meta.url)('playwright')
const root = resolve('dist'), queries = [], errors = []
let writes = 0
const server = createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost'), path = url.pathname
  const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' }); res.end(body) }
  if (path.startsWith('/ext/api/')) {
    if (req.method !== 'GET') { writes++; return send(405, 'application/json', '{}') }
    queries.push({ path, params: Object.fromEntries(url.searchParams) })
    let data
    if (path.endsWith('/auth/me')) data = { id: 1, sub2api_user_id: 1, username: '验收管理员', sub2api_role: 'admin' }
    else if (path.endsWith('/meta')) data = { categories: [{ value: 'CLOUD_SERVER', label: '云服务器' }], payers: [] }
    else if (path.endsWith('/monthly')) data = { total_amount: '0.00', count: 0, items: [], categories: [], people: [], scope: '按支出日期筛选', unconfirmed_count: 4 }
    else if (path.endsWith('/export')) return send(200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', Buffer.from('synthetic download'))
    else if (path.endsWith('/expense-records')) data = { items: [], total: 0, unconfirmed_count: 4 }
    else return send(404, 'application/json', '{}')
    return send(200, 'application/json', JSON.stringify(data))
  }
  if (path === '/frame') return send(200, 'text/html', `<style>body{margin:0}iframe{width:100%;height:1250px;border:0}</style><iframe title="Ops" src="/ext/app/admin/${url.searchParams.get('view') || 'expenses'}?ui_mode=iframe"></iframe>`)
  const file = resolve(root, path.replace(/^\/ext\/app\//, ''))
  if (file.startsWith(root + sep) && existsSync(file) && /\.(js|css)$/.test(file)) return send(200, file.endsWith('.js') ? 'application/javascript' : 'text/css', readFileSync(file))
  return send(200, 'text/html', readFileSync(resolve(root, 'index.html')))
})
await new Promise(done => server.listen(0, '127.0.0.1', done))
const base = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.OPS_BROWSER_EXECUTABLE || undefined })
const latest = path => queries.filter(q => q.path.endsWith(path)).at(-1)?.params
const responseFor = (page, endpoint, action) => Promise.all([page.waitForResponse(r => new URL(r.url()).pathname.endsWith(endpoint)), action()])
const datePart = p => ({ month: p.month, date_from: p.date_from, date_to: p.date_to })
try {
  for (const [width, theme] of [[1440, 'light'], [390, 'light'], [1440, 'dark']]) {
    for (const view of ['expenses', 'reports']) {
      const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
      await ctx.addCookies([{ name: 'ops_theme', value: theme, url: base + '/ext/app/' }])
      const page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message))
      await page.clock.setFixedTime(new Date('2026-10-11T04:00:00Z'))
      const endpoint = view === 'expenses' ? '/expense-records' : '/monthly'; await responseFor(page, endpoint, () => page.goto(`${base}/frame?view=${view}`))
      const frame = page.frameLocator('iframe')
      await frame.getByRole('heading', { name: view === 'expenses' ? '支出记录' : '月度开支', exact: true }).waitFor()
      assert.deepEqual(datePart(latest(endpoint)), { month: '', date_from: '2026-10-01', date_to: '2026-10-31' })
      assert.equal(await frame.getByText(/历史未核对|核对历史|历史单据/).count(), 0)
      assert.equal(await frame.getByRole('button', { name: '上月', exact: true }).count(), 0)
      const input = frame.locator('[data-test-id="dp-input"]')
      for (const [name, from, to] of [['上月', '2026-09-01', '2026-09-30'], ['本季度', '2026-10-01', '2026-12-31'], ['上季度', '2026-07-01', '2026-09-30'], ['本月', '2026-10-01', '2026-10-31']]) {
        await input.click()
        await responseFor(page, endpoint, () => frame.getByRole('button', { name, exact: true }).click())
        assert.deepEqual(datePart(latest(endpoint)), { month: '', date_from: from, date_to: to })
      }
      await input.click()
      const screenshotDir = process.env.OPS_DATE_SCREENSHOTS
      await frame.getByRole('button', { name: '上月', exact: true }).waitFor()
      if (screenshotDir) { mkdirSync(screenshotDir, { recursive: true }); await page.screenshot({ path: resolve(screenshotDir, `${view}-${width}-${theme}-calendar.png`), fullPage: true, animations: 'disabled' }) }
      // Select a custom cross-month range through the actual calendar cells.
      await frame.locator('[data-test-id="dp-2026-10-30"]').first().click()
      if (width === 390) await frame.getByRole('button', { name: '下个月', exact: true }).click()
      await frame.locator('[data-test-id="dp-2026-11-02"]').first().click()
      await responseFor(page, endpoint, () => frame.locator('[data-test-id="select-button"]').click())
      assert.deepEqual(datePart(latest(endpoint)), { month: '', date_from: '2026-10-30', date_to: '2026-11-02' })
      if (view === 'reports') {
        await responseFor(page, '/export', () => frame.getByRole('button', { name: '导出 Excel', exact: true }).click())
        assert.deepEqual(datePart(latest('/export')), datePart(latest(endpoint)))
      }
      await input.click(); await responseFor(page, endpoint, () => frame.getByRole('button', { name: '不限日期', exact: true }).click())
      assert.deepEqual(datePart(latest(endpoint)), { month: '', date_from: undefined, date_to: undefined })
      if (view === 'expenses') {
        await input.click(); await responseFor(page, endpoint, () => frame.getByRole('button', { name: '本月', exact: true }).click())
        await responseFor(page, endpoint, () => frame.getByRole('button', { name: '待报销', exact: true }).click())
        assert.equal(latest(endpoint).status, 'PENDING'); assert.equal(latest(endpoint).date_from, undefined)
      }
      if (width === 1440) {
        const boxes = await frame.locator('.ledger-filter .input, .ledger-filter .dp__input').evaluateAll(nodes => nodes.map(n => ({ y: n.getBoundingClientRect().y, height: n.getBoundingClientRect().height })))
        assert.ok(boxes.every(b => Math.abs(b.y - boxes[0].y) < 1 && b.height === 44), JSON.stringify(boxes))
      } else {
        const inner = page.frames().find(f => f.url().includes('/ext/app/'))
        assert.equal(await inner.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'No page-level horizontal overflow')
      }
      await ctx.close()
      console.log(`Passed: ${view}, ${width}px ${theme} iframe — sidebar presets, cross-month dates, unrestricted scope, no historical notices, aligned controls.`)
    }
  }
  assert.deepEqual(errors, []); assert.equal(writes, 0)
} finally { await browser.close(); await new Promise(done => server.close(done)) }
