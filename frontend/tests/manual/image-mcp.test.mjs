import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';

const core = await readFile(new URL('../../manual/assets/image-mcp-core.js', import.meta.url), 'utf8');
const sandbox = {}; vm.runInNewContext(core, sandbox);
const validRelease = sandbox.HuimaImageManual.validRelease;
const release = {schema:1, available:true, version:'0.1.0', url:'assets/downloads/HuimaImageSetup-0.1.0-win-x64.exe', sha256:'a'.repeat(64), bytes:123456789, signing:'unsigned-local'};

test('download gate accepts a complete local release and rejects missing or unsafe artifacts', () => {
  assert.equal(validRelease(release), true);
  for (const change of [{available:false}, {url:'https://example.com/setup.exe'}, {url:'assets/downloads/../../setup.exe'}, {bytes:0}, {bytes:'123'}, {sha256:'bad'}, {signing:'unknown'}]) {
    assert.equal(validRelease({...release,...change}), false);
  }
  assert.equal(validRelease(null), false);
});

test('tracked public manifest stays disabled until an authorized release', async () => {
  const published = JSON.parse(await readFile(new URL('../../manual/assets/image-mcp-release.json', import.meta.url), 'utf8'));
  assert.equal(published.available, false);
  assert.equal(validRelease(published), false);
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
