import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';
const core = await readFile(new URL('../../manual/assets/image-mcp-core.js', import.meta.url), 'utf8');
const sandbox = {}; vm.runInNewContext(core, sandbox);
const {validDownload, keyGuide} = sandbox.HuimaImageManual;
const cfg = JSON.parse(await readFile(new URL('../../manual/assets/manual-config.default.json', import.meta.url), 'utf8'));
const release = {...cfg.image_mcp.downloads.windows_x64, download_url:cfg.image_mcp.downloads.windows_x64.url};
test('download gate verifies metadata, safe file paths and platform extensions', () => {
  assert.equal(validDownload(release, 'windows_x64'), true);
  assert.equal(validDownload({...release, download_url:'/ext/api/v1/public/manual-files/12/setup.exe', file_name:'setup.exe'}, 'windows_x64'), true);
  assert.equal(validDownload({...release, download_url:'https://example.com/setup.exe', file_name:'setup.exe'}, 'windows_x64'), true);
  for (const change of [{enabled:false}, {download_url:'javascript:bad'}, {download_url:'assets/downloads/../setup.exe'}, {download_url:'/ext/api/v1/public/manual-files/1/%2e%2e%2fsetup.exe'}, {file_size:0}, {file_size:'123'}, {sha256:'bad'}, {signing:'unsigned-local'}, {version:''}, {system:''}, {file_name:'wrong.exe'}]) assert.equal(validDownload({...release,...change}, 'windows_x64'), false);
  assert.equal(validDownload(release, 'macos_arm64'), false);
  assert.equal(validDownload(null, 'windows_x64'), false);
});
test('key guide uses actual public group, known vendor only and generic fallback', () => {
  assert.match(keyGuide(null).body, /已开放生图模型/);
  const image = {recommended_group:{name:'测试组', platform:'openai', summary:'说明', notes:'条件'}, key_note:'附加'};
  assert.match(keyGuide(image).body, /「测试组」/);
  assert.match(keyGuide(image).detail, /OpenAI/);
  assert.equal(keyGuide({...image, recommended_group:{...image.recommended_group, platform:'unknown'}}).detail, '说明 · 条件');
  assert.equal(keyGuide(image).note, '附加');
});
test('image configuration does not participate in other manual section validation', async () => {
  const {isSafeConfig} = await import('../../manual/assets/manual-config-core.js');
  assert.equal(isSafeConfig({...cfg, image_mcp:{broken:true}}), true);
});

test('manual has local destinations, no duplicate anchors, and working section links', async () => {
  const root = new URL('../../manual/', import.meta.url);
  const page = await readFile(new URL('image-mcp.html', root), 'utf8');
  const ids = [...page.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
  assert.equal(ids.length, new Set(ids).size);
  for (const [,href] of page.matchAll(/href="(#[^"]+)"/g)) assert.ok(ids.includes(href.slice(1)), href);
  for (const [,src] of page.matchAll(/(?:src|href)="(assets\/[^"#]+)"/g)) await readFile(new URL(src, root));
  for (const filename of ['index.html','quick.html','cc-switch.html','groups.html']) {
    assert.match(await readFile(new URL(filename, root), 'utf8'), /href="image-mcp.html"/);
  }
});
