// Model filtering / recommendation rules and CC Switch import links, driven by the manual configuration.
import {derive} from './manual-config-core.js';

const TARGET_LABELS = Object.freeze({codex: 'Codex', claude: 'Claude Code'});
const MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;

export function validateApiKey(apiKey) {
  if (typeof apiKey !== 'string' || !apiKey || apiKey.length > 2048 || /[\s\x00-\x1f\x7f-\x9f]/u.test(apiKey)) {
    throw new Error('请粘贴完整 API Key，不能包含空格或换行。');
  }
  return apiKey;
}

// "Model ID + wildcard" patterns as configured by admins: * matches any run of characters, case-insensitive.
const compiled = new Map();
export function wildcard(pattern) {
  if (!compiled.has(pattern)) {
    const source = pattern.split('*').map(part => part.replace(/[.+?^${}()|[\]\\/]/g, '\\$&')).join('.*');
    compiled.set(pattern, new RegExp(`^${source}$`, 'i'));
  }
  return compiled.get(pattern);
}

const matchesAny = (id, patterns) => patterns.some(pattern => wildcard(pattern).test(id));

// Models of the key's group that this client may use: matches an include pattern and no exclude pattern.
export function parseAvailableModels(payload, client, cfg) {
  const rules = cfg.models[client];
  if (!rules) throw new Error('未知的客户端。');
  if (!Array.isArray(payload?.data)) throw new Error('模型接口返回格式不正确，请稍后重试。');
  const seen = new Set();
  return payload.data.flatMap(item => {
    const id = item?.id;
    if (typeof id !== 'string' || !MODEL_ID.test(id) || seen.has(id)) return [];
    if (!matchesAny(id, rules.include) || matchesAny(id, rules.exclude)) return [];
    seen.add(id);
    return [{id, label: typeof item.display_name === 'string' && item.display_name.trim()
      ? item.display_name.trim() : id}];
  });
}

// Claude Code model roles and the environment variable each one sets.
export const CLAUDE_ROLES = Object.freeze({
  fable: 'ANTHROPIC_DEFAULT_FABLE_MODEL',
  opus: 'ANTHROPIC_DEFAULT_OPUS_MODEL',
  sonnet: 'ANTHROPIC_DEFAULT_SONNET_MODEL',
  haiku: 'ANTHROPIC_DEFAULT_HAIKU_MODEL',
  subagent: 'CLAUDE_CODE_SUBAGENT_MODEL',
});

// Newest-looking ID matching the pattern: numeric-aware compare ranks claude-opus-5-5 above claude-opus-4-1.
export function newestMatch(ids, pattern) {
  return ids.filter(id => wildcard(pattern).test(id))
    .sort((a, b) => b.localeCompare(a, 'en', {numeric: true}))[0] || '';
}

function firstMatch(ids, patterns) {
  for (const pattern of patterns) {
    const match = newestMatch(ids, pattern);
    if (match) return match;
  }
  return '';
}

// Default model per client: the first configured pattern that matches wins; otherwise the first model.
export function recommendModel(ids, client, cfg) {
  return firstMatch(ids, cfg.models[client]?.recommend || []) || ids[0] || '';
}

// Map every role to a model the key's group actually serves, so no alias points at a missing model.
// Roles fall back to the main model; the subagent stays empty (Claude Code's own default) unless configured.
export function suggestClaudeRoles(ids, main, cfg) {
  const roles = cfg.claude_roles;
  return {
    fable: firstMatch(ids, roles.fable) || main,
    opus: firstMatch(ids, roles.opus) || main,
    sonnet: firstMatch(ids, roles.sonnet) || main,
    haiku: firstMatch(ids, roles.haiku) || main,
    subagent: firstMatch(ids, roles.subagent),
  };
}

export function validateClaudeRoles(roles = {}) {
  const valid = {};
  for (const role of Object.keys(CLAUDE_ROLES)) {
    const value = roles[role] || '';
    if (value && (typeof value !== 'string' || !MODEL_ID.test(value))) throw new Error('角色模型名称不正确，请重新读取模型。');
    valid[role] = value;
  }
  return valid;
}

export function getTargetDetails(target, cfg) {
  if (!Object.hasOwn(TARGET_LABELS, target)) return null;
  const {endpoints} = derive(cfg);
  return {
    label: TARGET_LABELS[target],
    endpoint: endpoints[target],
  };
}

export function validateImportInput({target, name, apiKey, model, roles} = {}) {
  if (!Object.hasOwn(TARGET_LABELS, target)) throw new Error('请选择 Codex 或 Claude Code。');
  if (typeof name !== 'string' || !name.trim() || name.length > 60 || /[\x00-\x1f\x7f]/u.test(name)) {
    throw new Error('请填写 1 到 60 字的配置名称。');
  }
  validateApiKey(apiKey);
  if (typeof model !== 'string' || !MODEL_ID.test(model)) {
    throw new Error('请选择模型。');
  }
  return {target, name: name.trim(), apiKey, model, roles: target === 'claude' ? validateClaudeRoles(roles) : {}};
}

export function buildImportUrl(input, cfg) {
  const {target, name, apiKey, model, roles} = validateImportInput(input);
  const params = new URLSearchParams({
    resource: 'provider', app: target, name,
    // Without homepage CC Switch infers it from the endpoint's parent domain, which is not our site.
    homepage: derive(cfg).site,
    endpoint: getTargetDetails(target, cfg).endpoint, apiKey, model, enabled: 'false',
  });
  if (target === 'claude') {
    // CC Switch has URL params for the haiku/sonnet/opus roles; other env vars ride in the inline JSON config.
    if (roles.haiku) params.set('haikuModel', roles.haiku);
    if (roles.sonnet) params.set('sonnetModel', roles.sonnet);
    if (roles.opus) params.set('opusModel', roles.opus);
    const env = {};
    if (roles.fable) env[CLAUDE_ROLES.fable] = roles.fable;
    if (roles.subagent) env[CLAUDE_ROLES.subagent] = roles.subagent;
    if (Object.keys(env).length) {
      const bytes = new TextEncoder().encode(JSON.stringify({env}));
      params.set('config', btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join('')));
      params.set('configFormat', 'json');
    }
  }
  return `ccswitch://v1/import?${params}`;
}
