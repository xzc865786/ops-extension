// Mac beginner route: page-side command builders, the JSON rules inside huima-config.sh, and the bash helpers.
// Run: node --test frontend/tests/manual/
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

import {
  MAC_INSTALL_DEFAULTS, buildMacConfigCommand, buildMacInstallCommand, buildMacRestoreCommand, scriptUrl,
} from '../../manual/assets/mac-command-core.js';

const DEFAULTS = JSON.parse(readFileSync(new URL('../../manual/assets/manual-config.default.json', import.meta.url), 'utf8'));
const clone = () => structuredClone(DEFAULTS);
const PAGE = 'https://api.tysy.top/docs/quick.html?os=mac#install';
const INSTALL_SH = new URL('../../manual/assets/downloads/huima-install.sh', import.meta.url);
const CONFIG_SH = new URL('../../manual/assets/downloads/huima-config.sh', import.meta.url);
const installText = readFileSync(INSTALL_SH, 'utf8');
const configText = readFileSync(CONFIG_SH, 'utf8');

// The pure half of the osascript engine is plain JavaScript; load it the way Node can.
const pureSource = configText.slice(configText.indexOf('// >>> pure'), configText.indexOf('// <<< pure'));
const engine = new Function(`${pureSource}; return {validateData, mergeClaudeSettings, markOnboarding, mergeCodexConfig, codexAuth, workbuddyEntry, mergeWorkbuddy, backupStamp, pickRestore};`)();

const decode = command => JSON.parse(Buffer.from(command.match(/bash -s -- '([A-Za-z0-9+/=]+)'$/)[1], 'base64').toString('utf8'));
const hasBash = spawnSync('bash', ['--version']).status === 0;
function bash(script) {
  const result = spawnSync('bash', ['-c', script], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('Mac scripts keep LF line endings and pass a bash syntax check', {skip: !hasBash && 'bash not available'}, () => {
  for (const [url, text] of [[INSTALL_SH, installText], [CONFIG_SH, configText]]) {
    assert.ok(!text.includes('\r'), `${url.pathname} must use LF line endings`);
    const result = spawnSync('bash', ['-n', url.pathname.replace(/^\/([A-Za-z]:)/, '$1')], {encoding: 'utf8'});
    assert.equal(result.status, 0, result.stderr);
  }
});

test('page defaults match the defaults inside huima-install.sh', () => {
  for (const [name, value] of Object.entries(MAC_INSTALL_DEFAULTS)) {
    assert.match(installText, new RegExp(`^${name}='${value.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}'$`, 'm'), name);
  }
  const install = DEFAULTS.install;
  assert.equal(MAC_INSTALL_DEFAULTS.HUIMA_NPM_REGISTRY, install.npm_registry);
  assert.equal(MAC_INSTALL_DEFAULTS.HUIMA_NODE_MIRROR, install.node_mirror);
  assert.equal(MAC_INSTALL_DEFAULTS.HUIMA_NODE_LTS, String(install.node_lts_major));
  assert.equal(MAC_INSTALL_DEFAULTS.HUIMA_CLAUDE_PACKAGE, install.claude_package);
  assert.equal(MAC_INSTALL_DEFAULTS.HUIMA_WORKBUDDY_SITE, install.workbuddy_site);
});

test('install command is short with defaults and carries only changed settings', () => {
  assert.equal(buildMacInstallCommand(['workbuddy', 'claude'], DEFAULTS, PAGE),
    "curl -fsSL 'https://api.tysy.top/docs/assets/downloads/huima-install.sh' | bash -s -- 'claude,workbuddy'");
  const cfg = clone();
  cfg.install.npm_registry = 'https://npm.example.cn';
  assert.match(buildMacInstallCommand(['codex'], cfg, PAGE), / 'codex' 'HUIMA_NPM_REGISTRY=https:\/\/npm\.example\.cn'$/);
  assert.throws(() => buildMacInstallCommand([], DEFAULTS, PAGE), /至少勾选/);
  cfg.install.npm_registry = "https://x.example/'$(id)";
  assert.throws(() => buildMacInstallCommand(['claude'], cfg, PAGE));
});

test('script URLs follow the page and reject anything a shell could reinterpret', () => {
  assert.equal(scriptUrl('huima-config.sh', 'https://ai.example.cn/docs/quick.html'), 'https://ai.example.cn/docs/assets/downloads/huima-config.sh');
  assert.equal(scriptUrl('huima-config.sh', 'http://localhost:18089/quick.html'), 'http://localhost:18089/assets/downloads/huima-config.sh');
  assert.throws(() => scriptUrl('huima-config.sh', 'http://api.tysy.top/docs/quick.html'));
  assert.throws(() => scriptUrl('huima-config.sh', "https://api.tysy.top/do'cs/quick.html"));
  assert.equal(buildMacRestoreCommand(PAGE), "curl -fsSL 'https://api.tysy.top/docs/assets/downloads/huima-config.sh' | bash -s -- '--restore'");
});

test('config command carries the same data as the Windows script and hides the key on screen', () => {
  const input = {
    claude: {apiKey: 'sk-claude-secret', model: 'claude-sonnet-5-5', roles: {opus: 'claude-opus-5-5'}},
    codex: {apiKey: 'sk-codex-secret', model: 'gpt-6.1-sol'},
  };
  const {command, preview} = buildMacConfigCommand(input, DEFAULTS, PAGE);
  const data = decode(command);
  assert.equal(data.tools.claude.apiKey, 'sk-claude-secret');
  assert.equal(data.settings.codex, 'https://api.tysy.top/v1');
  assert.ok(!preview.includes(command.match(/'([A-Za-z0-9+/=]{40,})'$/)[1]), 'the preview must not contain the data');
  assert.match(preview, /已隐藏/);
  assert.deepEqual(engine.validateData(data), ['claude', 'codex']);
  assert.throws(() => buildMacConfigCommand({claude: {apiKey: 'sk bad', model: 'claude-sonnet-5-5'}}, DEFAULTS, PAGE));
});

test('engine rejects tampered data before touching any file', () => {
  const good = decode(buildMacConfigCommand({workbuddy: {apiKey: 'sk-x', model: 'gpt-6.1-sol'}}, DEFAULTS, PAGE).command);
  assert.deepEqual(engine.validateData(good), ['workbuddy']);
  const bad = structuredClone(good);
  bad.settings.site = 'http://evil.example';
  assert.throws(() => engine.validateData(bad), /接口地址/);
  const badModel = structuredClone(good);
  badModel.tools.workbuddy.model = 'gpt"; rm -rf ~';
  assert.throws(() => engine.validateData(badModel), /模型/);
  assert.throws(() => engine.validateData({tools: {}, settings: good.settings}), /没有要配置/);
});

test('Claude Code settings keep unrelated fields and replace only the manual-owned ones', () => {
  const existing = {theme: 'dark', env: {ANTHROPIC_API_KEY: 'old', ANTHROPIC_MODEL: 'x', HTTP_PROXY: 'http://p', CLAUDE_CODE_SUBAGENT_MODEL: 'old-sub'}};
  const {settings, summary} = engine.mergeClaudeSettings(existing, 'sk-new', 'claude-sonnet-5-5', {opus: 'claude-opus-5-5', haiku: ''}, 'https://api.tysy.top');
  assert.deepEqual(settings, {
    theme: 'dark', model: 'claude-sonnet-5-5',
    env: {HTTP_PROXY: 'http://p', ANTHROPIC_BASE_URL: 'https://api.tysy.top', ANTHROPIC_AUTH_TOKEN: 'sk-new', ANTHROPIC_DEFAULT_OPUS_MODEL: 'claude-opus-5-5'},
  });
  assert.deepEqual(summary, ['Opus → claude-opus-5-5']);
  assert.equal(engine.mergeClaudeSettings(null, 'k', 'm', null, 'https://a.b').settings.env.ANTHROPIC_AUTH_TOKEN, 'k');
  assert.throws(() => engine.mergeClaudeSettings([], 'k', 'm', null, 'https://a.b'), /无法识别/);
});

test('onboarding flag is created, added or flipped without rewriting the rest of the file', () => {
  assert.equal(engine.markOnboarding(null).action, 'create');
  assert.equal(engine.markOnboarding('{"hasCompletedOnboarding": true}').action, 'done');
  const flipped = engine.markOnboarding('{\n  "numStartups": 3,\n  "hasCompletedOnboarding": false\n}');
  assert.equal(flipped.text, '{\n  "numStartups": 3,\n  "hasCompletedOnboarding": true\n}');
  const added = engine.markOnboarding('{\n  "numStartups": 3\n}');
  assert.deepEqual(JSON.parse(added.text), {hasCompletedOnboarding: true, numStartups: 3});
  assert.equal(engine.markOnboarding('{}').text, '{"hasCompletedOnboarding": true}');
  assert.equal(engine.markOnboarding('not json').action, 'skip');
});

test('Codex config keeps other settings and replaces our provider table', () => {
  const before = [
    'model = "o3"', 'approval_policy = "never"', '', '[model_providers.huima]', 'base_url = "https://old"',
    '', '[projects."/Users/a"]', 'trust_level = "trusted"',
  ].join('\n');
  const after = engine.mergeCodexConfig(before, 'gpt-6.1-sol', 'https://api.tysy.top/v1');
  assert.equal(after, [
    'model_provider = "huima"', 'model = "gpt-6.1-sol"', 'preferred_auth_method = "apikey"', '',
    'approval_policy = "never"', '', '[projects."/Users/a"]', 'trust_level = "trusted"', '',
    '[model_providers.huima]', 'name = "汇码"', 'base_url = "https://api.tysy.top/v1"', 'wire_api = "responses"', 'requires_openai_auth = true', '',
  ].join('\n'));
  assert.ok(!after.includes('https://old'));
  assert.deepEqual(JSON.parse(engine.codexAuth('sk-c')), {OPENAI_API_KEY: 'sk-c'});
});

test('WorkBuddy models keep the user\'s own entries and replace ours', () => {
  const settings = decode(buildMacConfigCommand({workbuddy: {apiKey: 'sk-w', model: 'gpt-6.1-sol'}}, DEFAULTS, PAGE).command).settings;
  const entry = engine.workbuddyEntry('sk-w', 'gpt-6.1-sol', settings);
  assert.equal(entry.url, 'https://api.tysy.top/v1/chat/completions');
  assert.equal(entry.maxInputTokens, DEFAULTS.workbuddy.max_input_tokens);
  const mine = {id: 'deepseek', url: 'https://other.example/v1'};
  const old = {id: 'gpt-5', url: 'https://api.tysy.top/v1/chat/completions'};
  assert.deepEqual(engine.mergeWorkbuddy(null, entry, settings.site), [entry]);
  assert.deepEqual(engine.mergeWorkbuddy([mine, old], entry, settings.site), [mine, entry]);
  const object = engine.mergeWorkbuddy({models: [old], availableModels: ['deepseek']}, entry, settings.site);
  assert.deepEqual(object, {models: [entry], availableModels: ['deepseek', 'gpt-6.1-sol']});
  assert.throws(() => engine.mergeWorkbuddy({models: 'x'}, entry, settings.site), /无法识别/);
});

test('restore picks the newest backup that is still active', () => {
  const files = [{path: '/a', existed: true, copy: 'file0.bak'}];
  const list = [
    {name: '20261005-101010', manifest: {status: 'active', files}},
    {name: '20261006-090000', manifest: {status: 'restored', files}},
    {name: '20261006-080000', manifest: {status: 'active', files}},
    {name: 'junk', manifest: null},
  ];
  assert.equal(engine.pickRestore(list).name, '20261006-080000');
  assert.equal(engine.pickRestore([{name: 'x', manifest: {status: 'restored', files}}]), null);
  assert.equal(engine.backupStamp(new Date(2026, 9, 6, 8, 5, 9)), '20261006-080509');
});

test('install script helpers: versions, tool choice and setting overrides', {skip: !hasBash && 'bash not available'}, () => {
  // Load the functions without running main (the last line).
  const load = `source <(sed '$d' '${INSTALL_SH.pathname.replace(/^\/([A-Za-z]:)/, '$1')}');`;
  assert.equal(bash(`${load} for v in '13.5 13.4.1' '13.5 13.5' '13.5 14.0' '14 13.6.1'; do set -- $v; version_ge $2 $1 && echo y || echo n; done`), 'n\ny\ny\nn\n');
  assert.equal(bash(`${load} choose_tools 'workbuddy,claude,claude,nope'`), 'workbuddy,claude');
  const out = bash(`${load} apply_setting 'HUIMA_NPM_REGISTRY=https://npm.example.cn'; apply_setting "HUIMA_CODEX_PACKAGE=@x/y;id"; apply_setting 'EVIL=1'; echo "$HUIMA_NPM_REGISTRY|$HUIMA_CODEX_PACKAGE"`);
  assert.match(out, /https:\/\/npm\.example\.cn\|@openai\/codex\n$/);
  assert.match(out, /格式不正确/);
  assert.match(out, /忽略未知参数/);
});

test('install script picks the newest LTS tarball from index.json, not the lagging alias', {skip: !hasBash && 'bash not available'}, () => {
  const load = `source <(sed '$d' '${INSTALL_SH.pathname.replace(/^\/([A-Za-z]:)/, '$1')}');`;
  const index = JSON.stringify([
    {version: 'v25.1.0', files: ['osx-arm64-tar'], lts: false},
    {version: 'v24.21.0', files: ['linux-x64', 'osx-arm64-tar', 'osx-x64-tar'], lts: 'Krypton'},
    {version: 'v24.9.0', files: ['osx-arm64-tar'], lts: 'Krypton'},
  ]);
  const sums = `${'a'.repeat(64)}  node-v24.21.0-darwin-arm64.tar.gz\n${'b'.repeat(64)}  node-v24.21.0-darwin-x64.tar.gz\n`;
  // Stub curl, not download: the real download() runs and its progress messages must not leak into the result.
  const script = `${load} WORK_DIR=$(mktemp -d); ARCH=arm64;
    curl() { local out='' url='' prev=''; for a in "$@"; do [ "$prev" = -o ] && out="$a"; prev="$a"; url="$a"; done;
      case "$url" in */index.json) printf '%s' '${index}' > "$out" ;; */SHASUMS256.txt) printf '${sums.replace(/\n/g, '\\n')}' > "$out" ;; *) return 1 ;; esac; };
    find_node_release https://mirror.example 2>/dev/null`;
  assert.equal(bash(script), `https://mirror.example v24.21.0 ${'a'.repeat(64)}\n`);
});
