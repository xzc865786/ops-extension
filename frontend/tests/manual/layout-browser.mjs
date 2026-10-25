// Layout/navigation regression against the actual manual with public config and download HEAD fixtures.
// Run with Playwright on NODE_PATH; OPS_BROWSER_EXECUTABLE optionally selects a local browser.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile, mkdir, writeFile, stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {extname, join, resolve, sep} from 'node:path';
const {chromium} = createRequire(import.meta.url)('playwright');
const root = fileURLToPath(new URL('../../manual/', import.meta.url));
const output = resolve(process.env.MANUAL_LAYOUT_OUTPUT || '../output/manual-layout-review');
const config = JSON.parse(await readFile(join(root, 'assets/manual-config.default.json'), 'utf8'));
const release = JSON.parse(await readFile(join(root, 'assets/image-mcp-release.json'), 'utf8'));
config.groups.items = [
  {name:'布局测试 · Claude', platform:'anthropic', clients:['claude'], badge:'recommended', rate_multiplier:1,
    billing_note:'仅用于本地布局测试', summary:'较短的分组描述。', suitable_for:['编程'], models:['claude-layout-test'], notes:''},
  {name:'布局测试 · Codex 与 WorkBuddy', platform:'openai', clients:['codex','workbuddy'], badge:'', rate_multiplier:1,
    billing_note:'本地布局测试，包含较长的计费说明，用于验证窄屏换行', summary:'这是一段较长的分组描述，用来检查不同长度的内容在同一排卡片中是否对齐。',
    suitable_for:['编程','文档与日常问答'], models:['gpt-layout-test-with-long-name'], notes:'仅供测试，不代表公开服务或价格。'},
];
const pages = ['index', 'quick', 'cc-switch', 'groups', 'image-mcp'];
const types = {'.html':'text/html', '.js':'application/javascript', '.json':'application/json', '.css':'text/css', '.svg':'image/svg+xml', '.jpg':'image/jpeg', '.png':'image/png', '.ico':'image/x-icon'};
const server = createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (!['GET', 'HEAD'].includes(req.method)) return res.writeHead(405).end();
  // Layout tests do not need the ignored 122 MiB binary; actual package validation belongs to release checks.
  if (pathname === `/docs/${release.url}` && req.method === 'HEAD') return res.writeHead(200, {'Content-Type':'application/octet-stream', 'Content-Length':release.bytes}).end();
  if (pathname === '/ext/api/v1/public/manual-config') return res.writeHead(200, {'Content-Type':'application/json'}).end(JSON.stringify({version:1, config}));
  if (!pathname.startsWith('/docs/')) return res.writeHead(404).end();
  const file = resolve(root, decodeURIComponent(pathname.slice(6)) || 'index.html');
  if (!file.startsWith(resolve(root) + sep)) return res.writeHead(404).end();
  try {
    res.writeHead(200, {'Content-Type':(types[extname(file)] || 'application/octet-stream') + '; charset=utf-8', 'Content-Length':(await stat(file)).size});
    res.end(req.method === 'HEAD' ? undefined : await readFile(file));
  }
  catch { res.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({headless:true, executablePath:process.env.OPS_BROWSER_EXECUTABLE || undefined});
const results = [], errors = [];
await mkdir(output, {recursive:true});
try {
  const context = await browser.newContext({reducedMotion:'reduce'});
  // No real service, model request, or external navigation is allowed by the test.
  await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  let commonNavigation;
  for (const width of [320, 360, 768, 1024, 1440]) {
    await page.setViewportSize({width, height:1000});
    for (const name of pages) {
      await page.goto(`${base}/docs/${name}.html?os=windows`, {waitUntil:'networkidle'});
      if (name === 'image-mcp' && release.available) assert.equal(await page.locator('#image-download').getAttribute('aria-disabled'), null, 'download button handles the release fixture');
      if (name === 'groups') assert.equal(await page.locator('.group-card').count(), 2);
      const navigation = await page.locator('#docs-sidebar nav > a').evaluateAll(links => links.map(link => ({
        text:link.textContent.trim(), href:link.pathname + (link.hash === '#start' ? '' : link.hash),
      })));
      commonNavigation ||= navigation;
      assert.deepEqual(navigation, commonNavigation, `${name}: full shared chapter list`);
      const links = await page.locator('#docs-sidebar a').evaluateAll(links => links.map(link => ({path:link.pathname.split('/').pop(), hash:link.hash.slice(1)})));
      for (const {path, hash} of links) {
        const html = await readFile(join(root, path), 'utf8');
        if (hash) assert.ok(html.includes(`id="${hash}"`), `${name}: broken link ${path}#${hash}`);
      }
      const layout = await page.evaluate(() => {
        const visible = element => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden';
        const overflow = [...document.querySelectorAll('#main-content *, .topbar *')].filter(element => {
          if (!visible(element) || element.closest('.sr-only, pre, .table-wrap, .field-table')) return false;
          const r = element.getBoundingClientRect();
          return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1);
        }).map(element => `${element.tagName}.${element.className}#${element.id}`);
        const grids = [...document.querySelectorAll('.card-grid, .group-list, .route-cards, .tool-grid')].filter(visible).map(grid => {
          const cards = [...grid.children].filter(visible).map(card => {
            const r = card.getBoundingClientRect();
            return {top:r.top, bottom:r.bottom, left:r.left, width:r.width, height:r.height, margin:getComputedStyle(card).marginTop};
          });
          return {className:grid.className, cards};
        });
        const controls = [...document.querySelector('.topbar').children].filter(visible).map(element => element.getBoundingClientRect());
        const headerOverlap = controls.some((a, i) => controls.slice(i + 1).some(b => Math.min(a.right,b.right) - Math.max(a.left,b.left) > 1 && Math.min(a.bottom,b.bottom) - Math.max(a.top,b.top) > 1));
        return {width:innerWidth, scrollWidth:document.documentElement.scrollWidth, overflow, headerOverlap, grids};
      });
      results.push({page:name, ...layout});
      if (width === 1440 || width === 360) await page.screenshot({path:join(output, `${name}-${width}.png`)});
      if (name === 'image-mcp') {
        await page.locator('#prepare').evaluate(section => scrollTo(0, section.offsetTop - document.querySelector('.topbar').offsetHeight));
        await page.screenshot({path:join(output, `preparations-${width}.png`)});
        const cards = await page.locator('.image-preparations > .card').evaluateAll(cards => cards.map(card => {
          const r = card.getBoundingClientRect(), link = card.querySelector('a').getBoundingClientRect();
          return {top:r.top, height:r.height, width:r.width, linkBottom:link.bottom};
        }));
        if (width > 700) for (const key of ['top','height','width','linkBottom']) assert.ok(Math.abs(cards[0][key] - cards[1][key]) < 1, `${width}: preparation ${key} must align`);
        if (width <= 800) {
          await page.locator('#menu-toggle').click();
          assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'true');
          await page.screenshot({path:join(output, `navigation-${width}.png`)});
          await page.keyboard.press('Escape');
          assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
        }
      }
      if ((width === 1440 || width === 360) && name !== 'image-mcp') {
        const selector = name === 'groups' ? '#groups' : name === 'quick' ? '#configure' : name === 'cc-switch' ? '#import' : '#api-key';
        await page.locator(selector).evaluate(section => scrollTo(0, section.offsetTop - document.querySelector('.topbar').offsetHeight));
        await page.screenshot({path:join(output, `${name}-content-${width}.png`)});
      }
    }
  }
  // Filtering this page must keep the other chapters reachable; colliding anchor names must stay distinct.
  await page.locator('#doc-search').fill('原图');
  await page.waitForFunction(() => document.querySelectorAll('mark.search-highlight').length > 0);
  assert.equal(await page.locator('#docs-sidebar a[href="index.html#contact"]').isVisible(), true);
  await page.locator('#doc-search').press('Escape');
  await page.locator('#docs-sidebar a[href="#prepare"]').click();
  await page.waitForFunction(() => document.querySelector('#docs-sidebar a[href="#prepare"]').getAttribute('aria-current') === 'location');
  await page.locator('#docs-sidebar a[href="index.html#api-key"]').click();
  await page.waitForURL('**/index.html#api-key');
  assert.equal(await page.locator('#docs-sidebar a[href="#api-key"]').count(), 1);
  const offline = await browser.newContext({javaScriptEnabled:false, viewport:{width:1440,height:1000}});
  const offlinePage = await offline.newPage();
  await offlinePage.goto(`${base}/docs/image-mcp.html`);
  assert.equal(await offlinePage.locator('#docs-sidebar nav > a').count(), commonNavigation.length);
  await offline.close();
  await writeFile(join(output, 'layout-results.json'), JSON.stringify({results, errors}, null, 2));
  for (const result of results) {
    assert.ok(result.scrollWidth <= result.width, `${result.page} at ${result.width}: page overflow`);
    assert.equal(result.headerOverlap, false, `${result.page} at ${result.width}: header controls overlap`);
    assert.deepEqual(result.overflow, [], `${result.page} at ${result.width}: element overflow`);
    for (const grid of result.grids) for (const card of grid.cards) assert.equal(card.margin, '0px', `${result.page}: grid card has extra top margin`);
  }
  assert.deepEqual(errors, []);
  console.log(`PASS: ${results.length} page/viewport layouts; shared navigation, links, card alignment, search, mobile menu and no-JS navigation.`);
  console.log(`Screenshots and measurements: ${output}`);
} finally {
  await browser.close();
  await new Promise(done => server.close(done));
}
