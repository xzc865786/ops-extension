const TARGETS = Object.freeze({
  codex: {label: 'Codex', endpoint: 'https://api.tysy.top/v1', platform: 'openai'},
  claude: {label: 'Claude Code', endpoint: 'https://api.tysy.top', platform: 'anthropic'},
});

export function validateApiKey(apiKey) {
  if (typeof apiKey !== 'string' || !apiKey || apiKey.length > 2048 || /[\s\x00-\x1f\x7f-\x9f]/u.test(apiKey)) {
    throw new Error('请粘贴完整 API Key，不能包含空格或换行。');
  }
  return apiKey;
}

// platform: 'openai' (Codex), 'anthropic' (Claude Code) or 'any' (Chat Completions clients such as WorkBuddy).
export function parseAvailableModels(payload, platform) {
  if (!['openai', 'anthropic', 'any'].includes(platform)) throw new Error('未知的模型平台。');
  if (!Array.isArray(payload?.data)) throw new Error('模型接口返回格式不正确，请稍后重试。');
  const seen = new Set();
  return payload.data.flatMap(item => {
    const id = item?.id;
    if (typeof id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(id) || seen.has(id)) return [];
    const owner = typeof item.owned_by === 'string' ? item.owned_by.toLowerCase() : '';
    const claudeModel = /^claude(?:-|$)/i.test(id);
    const openaiModel = /^(?:gpt-?\d|gpt-|o\d(?:-|$)|chatgpt-)/i.test(id);
    const matches = platform === 'any' ? true : platform === 'anthropic'
      ? claudeModel || (owner === 'anthropic' && !openaiModel)
      : openaiModel || (owner === 'openai' && !claudeModel);
    if (!matches) return [];
    seen.add(id);
    return [{id, label: typeof item.display_name === 'string' && item.display_name.trim()
      ? item.display_name.trim() : id}];
  });
}

const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;

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
  return ids.filter(id => pattern.test(id))
    .sort((a, b) => b.localeCompare(a, 'en', {numeric: true}))[0] || '';
}

// Map every role to a model the key's group actually serves, so no alias points at a missing model.
// The subagent model is left empty: Claude Code then uses each subagent's own default.
export function suggestClaudeRoles(ids, main) {
  const fable = newestMatch(ids, /fable/i);
  const opus = newestMatch(ids, /opus/i);
  const sonnet = newestMatch(ids, /sonnet/i);
  const haiku = newestMatch(ids, /haiku/i);
  return {
    fable: fable || opus || main,
    opus: opus || fable || main,
    sonnet: sonnet || main,
    haiku: haiku || sonnet || main,
    subagent: '',
  };
}

export function validateClaudeRoles(roles = {}) {
  const valid = {};
  for (const role of Object.keys(CLAUDE_ROLES)) {
    const value = roles[role] || '';
    if (value && (typeof value !== 'string' || !MODEL_PATTERN.test(value))) throw new Error('角色模型名称不正确，请重新读取模型。');
    valid[role] = value;
  }
  return valid;
}

// Default model per client, tried in order; both manual pages preselect the first match.
const PREFERRED_MODELS = Object.freeze({
  claude: [/sonnet/i, /opus/i],
  codex: [/^gpt-?6\.1-sol$/i, /^gpt-?6-luna$/i, /codex/i, /^gpt-5/i],
  // WorkBuddy accepts either vendor's key: Sonnet for an Anthropic key, otherwise the Codex defaults.
  workbuddy: [/sonnet/i, /^gpt-?6\.1-sol$/i, /^gpt-?6-luna$/i, /^gpt-5/i, /deepseek/i],
});

export function recommendModel(ids, client) {
  for (const pattern of PREFERRED_MODELS[client] || []) {
    const match = newestMatch(ids, pattern);
    if (match) return match;
  }
  return ids[0] || '';
}

export function validateImportInput({target, name, apiKey, model, roles} = {}) {
  if (!Object.hasOwn(TARGETS, target)) throw new Error('请选择 Codex 或 Claude Code。');
  if (typeof name !== 'string' || !name.trim() || name.length > 60 || /[\x00-\x1f\x7f]/u.test(name)) {
    throw new Error('请填写 1 到 60 字的配置名称。');
  }
  validateApiKey(apiKey);
  if (typeof model !== 'string' || !MODEL_PATTERN.test(model)) {
    throw new Error('请选择模型。');
  }
  return {target, name: name.trim(), apiKey, model, roles: target === 'claude' ? validateClaudeRoles(roles) : {}};
}

export function buildImportUrl(input) {
  const {target, name, apiKey, model, roles} = validateImportInput(input);
  const params = new URLSearchParams({
    resource: 'provider', app: target, name,
    endpoint: TARGETS[target].endpoint, apiKey, model, enabled: 'false',
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

export function getTargetDetails(target) {
  return TARGETS[target] || null;
}
