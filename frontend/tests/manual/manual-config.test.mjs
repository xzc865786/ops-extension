// Run: node --test frontend/tests/manual/
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

import {
  derive, formatRate, groupsForClient, isSafeConfig, isSafeGroups, platformLabel,
} from '../../manual/assets/manual-config-core.js';
import {
  buildImportUrl, parseAvailableModels, recommendModel, suggestClaudeRoles, wildcard,
} from '../../manual/assets/ccswitch-setup-core.js';
import {buildConfigCmd} from '../../manual/assets/quick-config-core.js';

const DEFAULTS = JSON.parse(readFileSync(new URL('../../manual/assets/manual-config.default.json', import.meta.url), 'utf8'));
const clone = () => structuredClone(DEFAULTS);
const payload = ids => ({data: ids.map(id => ({id}))});
const ids = list => list.map(model => model.id);

test('bundled defaults are considered safe', () => {
  assert.equal(isSafeConfig(DEFAULTS), true);
});

test('unsafe values make the whole configuration fall back', () => {
  const cases = [
    cfg => { cfg.site.url = 'http://api.tysy.top'; },
    cfg => { cfg.site.url = 'https://api.tysy.top/"&calc'; },
    cfg => { cfg.models.codex.recommend = ['gpt"; calc; "']; },
    cfg => { cfg.models.claude.include = []; },
    cfg => { cfg.claude_roles.haiku = ['$(whoami)']; },
    cfg => { cfg.install.claude_package = '@a/b && calc'; },
    cfg => { cfg.install.codex_store_id = '9plm9xgg6vks'; },
    cfg => { cfg.install.npm_registry = 'https://x.example/%25'; },
    cfg => { cfg.install.node_min_major = 30; },
    cfg => { cfg.workbuddy.max_input_tokens = '128000'; },
    cfg => { cfg.ccswitch.windows.url = 'javascript:alert(1)'; },
    cfg => { delete cfg.install; },
  ];
  for (const mutate of cases) {
    const cfg = clone();
    mutate(cfg);
    assert.equal(isSafeConfig(cfg), false, mutate.toString());
  }
});

test('wildcards match whole IDs, case-insensitively, without regex surprises', () => {
  assert.equal(wildcard('claude*').test('Claude-Sonnet-5-5'), true);
  assert.equal(wildcard('gpt-6.1-sol').test('gpt-6x1-sol'), false);
  assert.equal(wildcard('*codex*').test('gpt-5-codex'), true);
  assert.equal(wildcard('gpt-5*').test('xgpt-5'), false);
});

test('include / exclude rules filter the model list per client', () => {
  const list = payload(['claude-sonnet-5-5', 'gpt-6.1-sol', 'gpt6-luna', 'o3-mini', 'deepseek-v3', 'gpt-5-codex']);
  assert.deepEqual(ids(parseAvailableModels(list, 'claude', DEFAULTS)), ['claude-sonnet-5-5']);
  assert.deepEqual(ids(parseAvailableModels(list, 'codex', DEFAULTS)), ['gpt-6.1-sol', 'gpt6-luna', 'o3-mini', 'gpt-5-codex']);
  const cfg = clone();
  cfg.models.workbuddy.include.push('deepseek*');
  cfg.models.workbuddy.exclude = ['o3*'];
  assert.deepEqual(ids(parseAvailableModels(list, 'workbuddy', cfg)), ['gpt-6.1-sol', 'gpt6-luna', 'deepseek-v3', 'gpt-5-codex']);
});

test('recommendation follows the configured order', () => {
  assert.equal(recommendModel(['gpt-5', 'gpt-5-codex', 'gpt-6-luna', 'gpt-6.1-sol'], 'codex', DEFAULTS), 'gpt-6.1-sol');
  assert.equal(recommendModel(['gpt-5', 'gpt-5-codex', 'gpt-6-luna'], 'codex', DEFAULTS), 'gpt-6-luna');
  assert.equal(recommendModel(['claude-haiku-4-5', 'claude-sonnet-4-5', 'claude-sonnet-5-5'], 'claude', DEFAULTS), 'claude-sonnet-5-5');
  const cfg = clone();
  cfg.models.codex.recommend = ['gpt-6-luna'];
  assert.equal(recommendModel(['gpt-6.1-sol', 'gpt-6-luna'], 'codex', cfg), 'gpt-6-luna');
  cfg.models.codex.recommend = [];
  assert.equal(recommendModel(['gpt-6.1-sol', 'gpt-6-luna'], 'codex', cfg), 'gpt-6.1-sol');
});

test('Claude roles use configured patterns and fall back to the main model', () => {
  const models = ['claude-haiku-4-5', 'claude-sonnet-5-5', 'claude-opus-5-5'];
  assert.deepEqual(suggestClaudeRoles(models, 'claude-sonnet-5-5', DEFAULTS),
    {fable: 'claude-opus-5-5', opus: 'claude-opus-5-5', sonnet: 'claude-sonnet-5-5', haiku: 'claude-haiku-4-5', subagent: ''});
  assert.deepEqual(suggestClaudeRoles(['claude-sonnet-5-5'], 'claude-sonnet-5-5', DEFAULTS),
    {fable: 'claude-sonnet-5-5', opus: 'claude-sonnet-5-5', sonnet: 'claude-sonnet-5-5', haiku: 'claude-sonnet-5-5', subagent: ''});
  const cfg = clone();
  cfg.claude_roles.subagent = ['*haiku*'];
  assert.equal(suggestClaudeRoles(models, 'claude-sonnet-5-5', cfg).subagent, 'claude-haiku-4-5');
});

test('CC Switch import link and config script use the configured site address', () => {
  const cfg = clone();
  cfg.site.url = 'https://ai.example.cn';
  assert.deepEqual(derive(cfg).endpoints,
    {claude: 'https://ai.example.cn', codex: 'https://ai.example.cn/v1', workbuddy: 'https://ai.example.cn/v1/chat/completions'});
  const link = new URL(buildImportUrl({target: 'codex', name: '汇码 - Codex', apiKey: 'sk-test', model: 'gpt-6.1-sol'}, cfg)
    .replace('ccswitch://', 'http://x/'));
  assert.equal(link.searchParams.get('endpoint'), 'https://ai.example.cn/v1');
  assert.equal(link.searchParams.get('homepage'), 'https://ai.example.cn');

  cfg.workbuddy.max_input_tokens = 200000;
  const script = buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, cfg);
  const data = JSON.parse(Buffer.from(script.match(/FromBase64String\('([^']+)'\)/)[1], 'base64').toString('utf8'));
  assert.equal(data.settings.site, 'https://ai.example.cn');
  assert.equal(data.settings.workbuddy_url, 'https://ai.example.cn/v1/chat/completions');
  assert.equal(data.settings.workbuddy.max_input_tokens, 200000);
  assert.ok(!script.includes('api.tysy.top'), 'the old site must not be hardcoded in the script');

  cfg.site.url = 'https://evil.example/"&calc';
  assert.throws(() => buildConfigCmd({workbuddy: {apiKey: 'sk-test', model: 'gpt-6.1-sol'}}, cfg));
});

const GROUP = {
  name: 'Claude 稳定', platform: 'anthropic', clients: ['claude'], badge: 'recommended', rate_multiplier: 0.8,
  billing_note: '性价比高', summary: '日常编码首选', suitable_for: ['日常写代码'], models: ['claude-sonnet-5-5', 'claude-opus-*'],
  notes: '第一行\n第二行',
};

test('bundled group page and admin-shaped groups are safe', () => {
  assert.equal(isSafeGroups(DEFAULTS.groups), true);
  const groups = {...structuredClone(DEFAULTS.groups), items: [GROUP, {...GROUP, name: 'GPT', clients: ['codex', 'workbuddy'], badge: '', rate_multiplier: null}]};
  assert.equal(isSafeGroups(groups), true);
});

test('malformed groups are rejected without touching the rest of the configuration', () => {
  const cases = [
    groups => { groups.items = [{...GROUP, name: ''}]; },
    groups => { groups.items = [{...GROUP, name: 'a\nb'}]; },
    groups => { groups.items = [{...GROUP, clients: ['cursor']}]; },
    groups => { groups.items = [{...GROUP, badge: 'toString'}]; },
    groups => { groups.items = [{...GROUP, rate_multiplier: '0.8'}]; },
    groups => { groups.items = [{...GROUP, rate_multiplier: -1}]; },
    groups => { groups.items = [{...GROUP, models: ['gpt"; calc']}]; },
    groups => { groups.items = [{...GROUP, summary: 'bad\x07bell'}]; },
    groups => { groups.items = [{...GROUP, platform: 'Open AI'}]; },
    groups => { groups.faq = [{q: '问题', a: ''}]; },
    groups => { groups.intro = 'x'.repeat(501); },
    groups => { delete groups.items; },
  ];
  for (const mutate of cases) {
    const cfg = clone();
    mutate(cfg.groups);
    assert.equal(isSafeGroups(cfg.groups), false, mutate.toString());
    assert.equal(isSafeConfig(cfg), true);
  }
  assert.equal(isSafeGroups(undefined), false);
});

test('group helpers format rates, platforms and the software filter', () => {
  assert.equal(formatRate(0.8), '0.8×');
  assert.equal(formatRate(1), '1×');
  assert.equal(formatRate(0.123456), '0.1235×');
  assert.equal(formatRate(null), null);
  assert.equal(platformLabel('openai'), 'OpenAI');
  assert.equal(platformLabel('kimi'), 'kimi');
  const items = [GROUP, {...GROUP, name: 'GPT', clients: ['codex', 'workbuddy']}];
  assert.deepEqual(groupsForClient(items, 'all').map(g => g.name), ['Claude 稳定', 'GPT']);
  assert.deepEqual(groupsForClient(items, 'workbuddy').map(g => g.name), ['GPT']);
});
