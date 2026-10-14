// Browser integration for the real manual pages; all API calls use local fixtures and a fake key.
// Run with playwright available on NODE_PATH: node tests/manual/workbuddy-browser.mjs
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile, mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {extname, join, resolve, sep} from 'node:path';
const {chromium} = createRequire(import.meta.url)('playwright');
const root = fileURLToPath(new URL('../../manual/', import.meta.url));
const config = JSON.parse(await readFile(join(root, 'assets/manual-config.default.json'), 'utf8'));
config.models.workbuddy.include.push('gpt-strict', 'gpt-text-only');
config.workbuddy.capability_rules = [
  {models: ['gpt-text-only'], supports_images: false, supports_reasoning: false, can_disable_thinking: true},
  {models: ['gpt-strict'], supports_images: null, supports_reasoning: true, can_disable_thinking: true},
];
const types = {'.html': 'text/html', '.js': 'application/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg', '.png': 'image/png', '.ico': 'image/x-icon'};
const server = createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (!pathname.startsWith('/docs/')) { res.writeHead(404).end(); return; }
  const file = resolve(root, decodeURIComponent(pathname.slice(6)) || 'index.html');
  if (!file.startsWith(resolve(root) + sep)) { res.writeHead(404).end(); return; }
  try { res.writeHead(200, {'Content-Type': (types[extname(file)] || 'application/octet-stream') + '; charset=utf-8'}).end(await readFile(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({headless: true, executablePath: process.env.OPS_BROWSER_EXECUTABLE || undefined});
const context = await browser.newContext({viewport: {width: 1280, height: 900}});
const errors = [];
try {
  await context.route('**/ext/api/v1/public/manual-config', route => route.fulfill({json: {version: 1, config}}));
  await context.route('**/v1/models', route => {
    assert.equal(route.request().headers().authorization, 'Bearer sk-browser-test');
    return route.fulfill({json: {data: ['gpt-6.1-sol', 'gpt-strict', 'gpt-text-only', 'glm-5.3-flash', 'gpt-image-1', 'gpt-reserve'].map(id => ({id}))}});
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base + '/docs/quick.html?os=windows');
  for (const checkbox of await page.locator('input[name="config-tool"]').all()) await checkbox.uncheck();
  await page.locator('input[name="config-tool"][value="workbuddy"]').check();
  await page.locator('#key-workbuddy').fill('sk-browser-test');
  await page.locator('#load-models').click();
  await page.waitForFunction(() => !document.getElementById('model-workbuddy').disabled);
  assert.deepEqual(await page.locator('#model-workbuddy option').evaluateAll(options => options.map(option => option.value)),
    ['gpt-6.1-sol', 'gpt-strict', 'gpt-text-only', 'glm-5.3-flash']);
  assert.match(await page.locator('#workbuddy-capabilities').innerText(), /高；可选 低／中／高.*支持图片输入/);
  await page.locator('#model-workbuddy').selectOption('gpt-text-only');
  assert.match(await page.locator('#workbuddy-capabilities').innerText(), /仅支持文本输入/);
  await page.locator('#model-workbuddy').selectOption('glm-5.3-flash');
  assert.match(await page.locator('#workbuddy-capabilities').innerText(), /高；可选 低／中／高.*支持图片输入/);
  await page.locator('#model-workbuddy').selectOption('gpt-6.1-sol');
  await page.locator('#config-consent').check();
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#download-config').click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), 'huima-config.cmd');
  const script = await readFile(await download.path(), 'utf8');
  const data = JSON.parse(Buffer.from(script.match(/FromBase64String\('([^']+)'\)/)[1], 'base64').toString('utf8'));
  assert.equal(data.settings.workbuddy.supports_images, true);
  assert.equal(data.settings.workbuddy.default_effort, 'high');
  assert.equal(data.settings.workbuddy.max_input_tokens, null);
  assert.equal(await page.locator('#key-workbuddy').inputValue(), '');

  await page.goto(base + '/docs/cc-switch.html#workbuddy');
  await page.waitForFunction(() => document.getElementById('workbuddy-manual-summary').textContent.includes('支持图片输入'));
  assert.equal(await page.locator('[data-wb-setting="effort"]').innerText(), '高');
  assert.equal(await page.locator('[data-wb-setting="efforts"]').innerText(), '低、中、高');
  assert.equal(await page.locator('[data-wb-setting="images"]').innerText(), '勾选');
  assert.equal(await page.locator('[data-wb-setting="only"]').innerText(), '勾选');
  assert.equal(await page.locator('[data-wb-setting="disable"]').innerText(), '不勾选');
  await page.locator('#workbuddy-manual-model').fill('gpt-text-only');
  assert.match(await page.locator('[data-wb-setting="images"]').innerText(), /仅支持文本/);
  await page.locator('#workbuddy-manual-model').fill('gpt-strict');
  assert.equal(await page.locator('[data-wb-setting="only"]').innerText(), '不勾选');
  assert.equal(await page.locator('[data-wb-setting="disable"]').innerText(), '勾选');
  await page.locator('#workbuddy-manual-model').fill('gpt-6.1-sol');
  if (process.env.OPS_MANUAL_SHOTS) {
    await mkdir(process.env.OPS_MANUAL_SHOTS, {recursive: true});
    await page.locator('#workbuddy').screenshot({path: join(process.env.OPS_MANUAL_SHOTS, 'workbuddy-desktop.png'), style: '.topbar,.skip-link { visibility:hidden; }'});
  }
  await page.setViewportSize({width: 390, height: 844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  if (process.env.OPS_MANUAL_SHOTS) await page.locator('#workbuddy').screenshot({path: join(process.env.OPS_MANUAL_SHOTS, 'workbuddy-mobile.png'), style: '.topbar,.skip-link { visibility:hidden; }'});
  // Optional real Vue + isolated backend check (tests.serve_ledger_browser, never production).
  if (process.env.OPS_BROWSER_BASE_URL) {
    const ops = process.env.OPS_BROWSER_BASE_URL;
    const opsUrl = new URL(ops);
    assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(opsUrl.hostname), '后台写入验收仅允许本地隔离测试地址');
    const token = 'dev:' + JSON.stringify({id: 9901, username: '页面测试管理员', role: 'admin'});
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${ops}/ext/auth/bootstrap?token=${encodeURIComponent(token)}&next=/ext/app/admin/manual`);
    const api = async (path, options) => {
      const response = await context.request.fetch(ops + '/ext/api/v1/admin/manual' + path, options);
      assert.ok(response.ok(), await response.text());
      return response.json();
    };
    const before = await api('/config');
    const legacy = structuredClone(before.config);
    for (const key of ['capability_rules', 'default_effort', 'supported_efforts']) delete legacy.workbuddy[key];
    Object.assign(legacy.workbuddy, {supports_reasoning: false, max_input_tokens: 128000, max_output_tokens: 8192});
    await api('/config', {method: 'PUT', data: {config: legacy, base_version: before.version, note: '隔离测试：旧配置'}});
    await page.reload();
    await page.getByRole('button', {name: '安装与客户端', exact: true}).click();
    const section = page.locator('section').filter({hasText: 'WorkBuddy 模型参数'});
    assert.equal(await section.locator('input[type="number"]').nth(0).inputValue(), '128000');
    await section.getByRole('button', {name: '应用 WorkBuddy 推荐配置', exact: true}).click();
    assert.equal(await section.locator('input[type="number"]').nth(0).inputValue(), '');
    await section.locator('input[type="number"]').nth(1).fill('32000');
    await section.getByLabel('默认开启图片输入').uncheck();
    const published = page.waitForResponse(response => response.url().endsWith('/admin/manual/config') && response.request().method() === 'PUT');
    await page.getByRole('button', {name: '保存并生效', exact: true}).click();
    assert.equal((await published).status(), 200);
    const saved = await api('/config');
    assert.equal(saved.config.workbuddy.default_effort, 'high');
    assert.deepEqual(saved.config.workbuddy.supported_efforts, ['low', 'medium', 'high']);
    assert.equal(saved.config.workbuddy.max_input_tokens, null);
    assert.equal(saved.config.workbuddy.max_output_tokens, 32000);
    assert.equal(saved.config.workbuddy.supports_images, false);
    assert.deepEqual(saved.config.workbuddy.capability_rules, []);
    assert.deepEqual(saved.config.site, before.config.site);
    await section.locator('input[type="number"]').nth(1).fill('');
    await section.locator('input[type="checkbox"][value="high"]').uncheck();
    const rejected = page.waitForResponse(response => response.url().endsWith('/admin/manual/config') && response.request().method() === 'PUT');
    await page.getByRole('button', {name: '保存并生效', exact: true}).click();
    assert.equal((await rejected).status(), 422);
    await section.locator('input[type="checkbox"][value="high"]').check();
    const cleared = page.waitForResponse(response => response.url().endsWith('/admin/manual/config') && response.request().method() === 'PUT');
    await page.getByRole('button', {name: '保存并生效', exact: true}).click();
    assert.equal((await cleared).status(), 200);
    assert.equal((await api('/config')).config.workbuddy.max_output_tokens, null);
    console.log('后台浏览器验收通过：旧配置升级、默认图片开关、可空上限、发布与思考档位校验。');
  }
  assert.deepEqual(errors, []);
  console.log('手册浏览器验收通过：模型切换、能力提示、下载配置、按图推荐表、移动布局；未调用真实模型接口。');
} finally {
  await browser.close();
  await new Promise(done => server.close(done));
}
