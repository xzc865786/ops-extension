// Pure helpers for the manual configuration (no network, no DOM), shared by pages, scripts and tests.

// Mirrors backend/app/manual/schema.py.
const PATTERN = /^[A-Za-z0-9.*_:/-]{1,128}$/;
const HTTPS_URL = /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?(\/[A-Za-z0-9._~/-]*)?$/;
const SITE_URL = /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/;
const DOWNLOAD = /^(https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?(\/[A-Za-z0-9._~/%-]*)?|assets\/downloads\/[A-Za-z0-9._-]{1,120}|\/ext\/api\/v1\/public\/manual-files\/\d+\/[A-Za-z0-9._~%()+-]{1,600})$/;
const NPM_PACKAGE = /^(@[a-z0-9][a-z0-9._-]{0,100}\/)?[a-z0-9][a-z0-9._-]{0,100}$/;
const STORE_ID = /^[A-Z0-9]{12}$/;
const WINGET_ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,63}(\.[A-Za-z0-9][A-Za-z0-9-]{0,63}){1,3}$/;
const VERSION = /^\d{1,4}\.\d{1,4}\.\d{1,6}$/;
const QQ = /^(\d{5,12})?$/;

const patterns = list => Array.isArray(list) && list.every(item => typeof item === 'string' && PATTERN.test(item));
const int = (value, min, max) => Number.isInteger(value) && value >= min && value <= max;

export function isSafeConfig(cfg) {
  try {
    const {site, contact, announcement, models, claude_roles: roles, workbuddy: wb, install, ccswitch} = cfg;
    return SITE_URL.test(site.url) && QQ.test(contact.qq)
      && typeof announcement.enabled === 'boolean' && typeof announcement.text === 'string' && announcement.text.length <= 300
      && ['claude', 'codex', 'workbuddy'].every(client => patterns(models[client].include) && models[client].include.length > 0
        && patterns(models[client].exclude) && patterns(models[client].recommend))
      && ['fable', 'opus', 'sonnet', 'haiku', 'subagent'].every(role => patterns(roles[role]))
      && int(wb.max_input_tokens, 1024, 2000000) && int(wb.max_output_tokens, 256, 1000000)
      && ['supports_tool_call', 'supports_images', 'supports_reasoning'].every(key => typeof wb[key] === 'boolean')
      && ['npm_registry', 'npm_registry_fallback', 'node_mirror', 'workbuddy_site'].every(key => HTTPS_URL.test(install[key]))
      && int(install.node_min_major, 18, 60) && int(install.node_lts_major, 18, 60) && install.node_min_major <= install.node_lts_major
      && NPM_PACKAGE.test(install.claude_package) && NPM_PACKAGE.test(install.codex_package)
      && STORE_ID.test(install.codex_store_id) && WINGET_ID.test(install.workbuddy_winget_id)
      && int(install.workbuddy_size_mb, 1, 10000)
      && VERSION.test(ccswitch.version) && HTTPS_URL.test(ccswitch.releases_url)
      && DOWNLOAD.test(ccswitch.windows.download_url ?? ccswitch.windows.url);
  } catch {
    return false;
  }
}

// Values derived from the configuration that pages and scripts need.
export function derive(cfg) {
  const site = cfg.site.url;
  return {
    site,
    host: site.replace(/^https:\/\//, ''),
    endpoints: {claude: site, codex: `${site}/v1`, workbuddy: `${site}/v1/chat/completions`},
    ccswitchDownload: cfg.ccswitch.windows.download_url ?? cfg.ccswitch.windows.url,
  };
}

// ---- Group page --------------------------------------------------------------
// Plain text only (rendered with textContent); mirrors the limits in backend GroupInfo / Groups.

export const GROUP_CLIENTS = [
  {key: 'claude', label: 'Claude Code'},
  {key: 'codex', label: 'Codex'},
  {key: 'workbuddy', label: 'WorkBuddy'},
];
export const GROUP_BADGES = {recommended: '推荐', stable: '稳定', value: '实惠', limited: '限时', exclusive: '专属'};
const PLATFORM_LABELS = {anthropic: 'Anthropic', openai: 'OpenAI', gemini: 'Gemini'};
const CONTROL = /[\x00-\x09\x0b-\x1f\x7f]/;

const text = (value, max, multiline = true) => typeof value === 'string' && value.length <= max
  && !CONTROL.test(value) && (multiline || !value.includes('\n'));

function isSafeGroup(item) {
  return item && typeof item === 'object' && text(item.name, 64, false) && item.name.length > 0
    && text(item.platform ?? '', 32) && /^[a-z0-9_]*$/.test(item.platform ?? '')
    && Array.isArray(item.clients) && item.clients.every(client => GROUP_CLIENTS.some(c => c.key === client))
    && (item.badge === '' || item.badge === undefined || Object.prototype.hasOwnProperty.call(GROUP_BADGES, item.badge))
    && (item.rate_multiplier === null || item.rate_multiplier === undefined
      || (typeof item.rate_multiplier === 'number' && Number.isFinite(item.rate_multiplier) && item.rate_multiplier >= 0 && item.rate_multiplier <= 1000))
    && text(item.billing_note ?? '', 200) && text(item.summary ?? '', 200) && text(item.notes ?? '', 500)
    && Array.isArray(item.suitable_for) && item.suitable_for.length <= 8 && item.suitable_for.every(entry => text(entry, 80, false))
    && patterns(item.models) && item.models.length <= 30;
}

export function isSafeGroups(groups) {
  try {
    return text(groups.intro, 500) && text(groups.notice, 300)
      && Array.isArray(groups.items) && groups.items.length <= 30 && groups.items.every(isSafeGroup)
      && Array.isArray(groups.faq) && groups.faq.length <= 20
      && groups.faq.every(entry => text(entry.q, 100) && text(entry.a, 500) && entry.q && entry.a);
  } catch {
    return false;
  }
}

export function platformLabel(platform) {
  return PLATFORM_LABELS[platform] || platform || '';
}

// 0.8 -> "0.8×", 1 -> "1×", 0.125 -> "0.125×"; null when the admin chose not to show a number.
export function formatRate(multiplier) {
  if (typeof multiplier !== 'number' || !Number.isFinite(multiplier)) return null;
  return `${Number(multiplier.toFixed(4))}×`;
}

export function groupsForClient(items, client) {
  return client === 'all' ? items : items.filter(item => item.clients.includes(client));
}
