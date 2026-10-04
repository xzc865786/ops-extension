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
