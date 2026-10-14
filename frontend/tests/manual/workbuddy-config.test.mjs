import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, mkdtempSync, mkdirSync, existsSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import {resolveWorkBuddy, workbuddySummary} from '../../manual/assets/workbuddy-config-core.js';
import {isSafeConfig} from '../../manual/assets/manual-config-core.js';
import {buildConfigCmd, buildRollbackCmd} from '../../manual/assets/quick-config-core.js';
import {buildMacConfigCommand} from '../../manual/assets/mac-command-core.js';
import {windowsPowerShellDiscovery} from '../../manual/assets/windows-powershell.js';
import {buildRollbackCmd as buildLegacyRollbackCmd} from '../../manual/assets/codex-setup-core.js';

const defaults = JSON.parse(readFileSync(new URL('../../manual/assets/manual-config.default.json', import.meta.url), 'utf8'));
const clone = () => structuredClone(defaults);
const decode = script => JSON.parse(Buffer.from(script.match(/FromBase64String\('([^']+)'\)/)[1], 'base64').toString('utf8'));
const configText = readFileSync(new URL('../../manual/assets/downloads/huima-config.sh', import.meta.url), 'utf8');
const pure = configText.slice(configText.indexOf('// >>> pure'), configText.indexOf('// <<< pure'));
const macEngine = new Function(`${pure}; return {workbuddyEntry,validateData};`)();

test('unmatched models use the WorkBuddy defaults; rules override only what they set, exact IDs first', () => {
  for (const model of ['gpt-6.1-sol', 'deepseek-v4.1-flash', 'glm-5.3-flash']) {
    const wb = resolveWorkBuddy(model, defaults);
    // WorkBuddy keeps its own on/off switch (default off), so the default is "仅思考模式".
    assert.deepEqual([wb.supports_reasoning, wb.supports_images, wb.only_reasoning, wb.can_disable_thinking], [true, true, true, false], model);
  }
  assert.match(workbuddySummary('gpt-6.1-sol', defaults), /高；可选 低／中／高.*支持图片输入/);
  const cfg = clone();
  cfg.workbuddy.capability_rules = [
    {models: ['glm*'], supports_images: false, supports_reasoning: null, can_disable_thinking: true},
    {models: ['glm-text-only'], supports_images: null, supports_reasoning: false, can_disable_thinking: true},
    {models: ['gpt-strict'], supports_images: null, supports_reasoning: true, can_disable_thinking: false},
  ];
  const wildcard = resolveWorkBuddy('glm-5.3-flash', cfg);
  assert.deepEqual([wildcard.supports_images, wildcard.supports_reasoning, wildcard.only_reasoning], [false, true, false]);
  const exact = resolveWorkBuddy('GLM-TEXT-ONLY', cfg);
  assert.deepEqual([exact.supports_images, exact.supports_reasoning], [true, false]);
  assert.match(workbuddySummary('glm-text-only', cfg), /不开启思考/);
  assert.equal(resolveWorkBuddy('gpt-strict', cfg).only_reasoning, true);
  Object.assign(cfg.workbuddy, {supports_images: false, supports_reasoning: false});
  const off = resolveWorkBuddy('deepseek-v4.1-flash', cfg);
  assert.deepEqual([off.supports_images, off.supports_reasoning], [false, false]);
  assert.equal(resolveWorkBuddy('gpt-strict', cfg).supports_reasoning, true);
  assert.match(workbuddySummary('deepseek-v4.1-flash', cfg), /仅支持文本输入/);
});

test('invalid strengths, duplicate rules and invalid limits are rejected before script generation', () => {
  for (const mutate of [
    wb => { wb.supported_efforts = ['low']; },
    wb => { wb.supported_efforts = ['high', 'high']; },
    wb => { wb.default_effort = 'max'; },
    wb => { wb.max_input_tokens = 0; },
    wb => { wb.capability_rules.push({...wb.capability_rules[0]}); },
    wb => { wb.capability_rules[0].models = ['*']; },
    wb => { wb.capability_rules[0].supports_images = 'true'; },
    wb => { wb.capability_rules[0].supports_reasoning = 'yes'; },
  ]) {
    const cfg = clone();
    cfg.workbuddy.capability_rules = [{models: ['glm*'], supports_images: false, supports_reasoning: null, can_disable_thinking: true}];
    assert.equal(isSafeConfig(cfg), true);
    mutate(cfg.workbuddy);
    assert.equal(isSafeConfig(cfg), false, mutate.toString());
    assert.throws(() => buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, cfg));
  }
});

test('Windows and Mac resolve the same per-model configuration and omit unset limits', () => {
  for (const model of ['gpt-6.1-sol', 'gpt-5.5', 'deepseek-v4.1-flash', 'glm-5.3-flash']) {
    const input = {workbuddy: {apiKey: 'sk-test', model}};
    const windows = decode(buildConfigCmd(input, defaults));
    const command = buildMacConfigCommand(input, defaults, 'https://example.cn/docs/quick.html').command;
    const mac = JSON.parse(Buffer.from(command.match(/bash -s -- '([^']+)'$/)[1], 'base64').toString('utf8'));
    assert.deepEqual(windows, mac);
    macEngine.validateData(mac);
    const entry = macEngine.workbuddyEntry('sk-test', model, mac.settings);
    assert.equal(Object.hasOwn(entry, 'maxInputTokens'), false);
    assert.equal(Object.hasOwn(entry, 'maxOutputTokens'), false);
    if (entry.supportsReasoning) {
      assert.equal(entry.reasoning.defaultEffort, 'high');
      assert.deepEqual(entry.reasoning.supportedEfforts, ['low', 'medium', 'high']);
      assert.equal(entry.onlyReasoning && entry.reasoning.canDisableThinking, false);
    } else assert.equal(Object.hasOwn(entry, 'reasoning'), false);
  }
  const cfg = clone(); cfg.workbuddy.max_output_tokens = 32000;
  const data = decode(buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, cfg));
  assert.equal(macEngine.workbuddyEntry('sk-test', 'gpt-6.1-sol', data.settings).maxOutputTokens, 32000);
  data.settings.workbuddy.supported_efforts = ['max'];
  assert.throws(() => macEngine.validateData(data), /能力配置异常/);
});

test('install, configure and restore embed the same PowerShell discovery routines', () => {
  const install = readFileSync(new URL('../../manual/assets/downloads/huima-install.cmd', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
  const config = buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, defaults).replace(/\r\n/g, '\n');
  for (const script of [install, config, buildRollbackCmd(), buildLegacyRollbackCmd()].map(text => text.replace(/\r\n/g, '\n'))) {
    assert.ok(script.includes(windowsPowerShellDiscovery));
    assert.match(script, /call :HUIMA_FIND_PS/);
    assert.match(script, /"%HUIMA_PS%" -NoLogo -NoProfile/);
  }
});

const windows = process.platform === 'win32';
const legacyPS = join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
const ps7 = windows ? spawnSync(join(process.env.SystemRoot, 'System32', 'where.exe'), ['pwsh.exe'], {encoding: 'utf8'}).stdout?.trim().split(/\r?\n/)[0] : '';
const cmd = process.env.ComSpec;
function sandboxScript(script, directory) {
  const source = "$script:UserHome = [Environment]::GetFolderPath('UserProfile')";
  assert.ok(script.includes(source));
  return script.replace(source, `$script:UserHome = '${directory.replace(/'/g, "''")}'`);
}
function runCmd(file, input, env) {
  const result = spawnSync(cmd, ['/d', '/c', file], {input, encoding: 'utf8', env: {...process.env, HUIMA_NO_PAUSE: '1', ...env}, timeout: 30000});
  assert.equal(result.status, 0, result.stdout + result.stderr + (result.error || ''));
}

test('Windows configuration and restore work without PATH, including existing JSON-array backups', {skip: !windows || !existsSync(legacyPS)}, () => {
  const directory = mkdtempSync(join(tmpdir(), 'huima-workbuddy-test-'));
  try {
    const file = join(directory, '.workbuddy', 'models.json');
    mkdirSync(join(directory, '.workbuddy'));
    const original = '[{"id":"other","url":"https://other.example/v1","custom":true}]';
    writeFileSync(file, original);
    const script = sandboxScript(buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, defaults), directory);
    const config = join(directory, '配置.cmd'); writeFileSync(config, script);
    runCmd(config, 'Y\nN\n', {PATH: ''});
    const entries = JSON.parse(readFileSync(file, 'utf8'));
    assert.equal(entries.length, 2);
    assert.equal(entries[0].custom, true);
    assert.equal(entries[1].reasoning.defaultEffort, 'high');
    assert.equal(entries[1].supportsImages, true);
    assert.equal(Object.hasOwn(entries[1], 'maxOutputTokens'), false);
    const restore = join(directory, '恢复.cmd'); writeFileSync(restore, sandboxScript(buildRollbackCmd(), directory));
    runCmd(restore, 'Y\n', {PATH: ''});
    assert.equal(readFileSync(file, 'utf8'), original);
  } finally { rmSync(directory, {recursive: true, force: true}); }
});

test('Windows launcher falls back to installed PowerShell 7 before any configuration', {skip: !windows || !ps7}, () => {
  const directory = mkdtempSync(join(tmpdir(), 'huima-pwsh-test-'));
  try {
    const file = join(directory, 'config.cmd');
    const script = sandboxScript(buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, defaults), directory);
    writeFileSync(file, script);
    // Resolve the installed PowerShell/7 parent; hide the legacy Windows executable in this child's environment only.
    const programFiles = resolve(ps7, '..', '..', '..');
    runCmd(file, 'Y\nN\n', {SystemRoot: directory, ProgramFiles: programFiles, ProgramW6432: programFiles, PATH: ''});
    const entries = JSON.parse(readFileSync(join(directory, '.workbuddy', 'models.json'), 'utf8'));
    assert.equal(entries[0].reasoning.defaultEffort, 'high');
  } finally { rmSync(directory, {recursive: true, force: true}); }
});

test('no usable PowerShell stops before writing configuration', {skip: !windows}, () => {
  const directory = mkdtempSync(join(tmpdir(), 'huima-no-engine-test-'));
  try {
    const file = join(directory, 'config.cmd');
    writeFileSync(file, sandboxScript(buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, defaults), directory));
    const result = spawnSync(cmd, ['/d', '/c', file], {
      encoding: 'utf8', timeout: 30000,
      env: {...process.env, SystemRoot: directory, ProgramFiles: directory, ProgramW6432: directory, PATH: '', HUIMA_NO_PAUSE: '1'},
    });
    assert.equal(result.status, 1);
    assert.match(result.stdout, /PowerShell/);
    assert.equal(existsSync(join(directory, '.workbuddy')), false);
    assert.equal(existsSync(join(directory, '.huima')), false);
  } finally { rmSync(directory, {recursive: true, force: true}); }
});
