/* One-line Terminal commands for the Mac beginner route. The scripts live next to the manual. */
// macOS marks downloaded script files as untrusted and drops their execute bit, so beginners
// paste one line into Terminal instead: curl fetches the script from this site and bash runs it.

import {base64Utf8, scriptSettings, validateConfigInput} from './quick-config-core.js';
import {isSafeConfig} from './manual-config-core.js';

const INSTALL_TOOLS = ['claude', 'codex', 'workbuddy'];
// Mirrors the defaults at the top of huima-install.sh; only values that differ go on the command line.
export const MAC_INSTALL_DEFAULTS = Object.freeze({
  HUIMA_NPM_REGISTRY: 'https://registry.npmmirror.com',
  HUIMA_NPM_REGISTRY_FALLBACK: 'https://registry.npmjs.org',
  HUIMA_NODE_MIRROR: 'https://registry.npmmirror.com/-/binary/node',
  HUIMA_NODE_MIN: '22',
  HUIMA_NODE_LTS: '24',
  HUIMA_CLAUDE_PACKAGE: '@anthropic-ai/claude-code',
  HUIMA_CODEX_PACKAGE: '@openai/codex',
  HUIMA_WORKBUDDY_SITE: 'https://www.workbuddy.cn/',
});
const SAFE_WORD = /^[A-Za-z0-9._~:/@%,=+-]+$/;

// Only https (the live site), file (tests) or a local preview server, and nothing a shell could reinterpret.
export function scriptUrl(name, base) {
  const url = new URL(`assets/downloads/${name}`, base);
  const local = url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname);
  if (!(['https:', 'file:'].includes(url.protocol) || local) || !SAFE_WORD.test(url.href)) throw new Error('手册地址异常，请刷新页面后重试。');
  return url.href;
}

function quote(word) {
  if (!SAFE_WORD.test(word)) throw new Error('手册配置异常，请刷新页面后重试。');
  return `'${word}'`;
}

function pipe(name, base, args) {
  return `curl -fsSL ${quote(scriptUrl(name, base))} | bash -s -- ${args.map(quote).join(' ')}`;
}

export function buildMacInstallCommand(tools, cfg, base) {
  const picked = INSTALL_TOOLS.filter(tool => tools.includes(tool));
  if (!picked.length) throw new Error('请至少勾选一个要安装的软件。');
  if (!isSafeConfig(cfg)) throw new Error('手册配置异常，请刷新页面后重试。');
  const install = cfg.install;
  const values = {
    HUIMA_NPM_REGISTRY: install.npm_registry,
    HUIMA_NPM_REGISTRY_FALLBACK: install.npm_registry_fallback,
    HUIMA_NODE_MIRROR: install.node_mirror,
    HUIMA_NODE_MIN: install.node_min_major,
    HUIMA_NODE_LTS: install.node_lts_major,
    HUIMA_CLAUDE_PACKAGE: install.claude_package,
    HUIMA_CODEX_PACKAGE: install.codex_package,
    HUIMA_WORKBUDDY_SITE: install.workbuddy_site,
  };
  const settings = Object.entries(values)
    .filter(([name, value]) => String(value) !== MAC_INSTALL_DEFAULTS[name])
    .map(([name, value]) => `${name}=${value}`);
  return pipe('huima-install.sh', base, [picked.join(','), ...settings]);
}

// Returns the command to copy and a masked version that is safe to show on screen.
export function buildMacConfigCommand(input, cfg, base) {
  const tools = validateConfigInput(input);
  const data = base64Utf8(JSON.stringify({tools, settings: scriptSettings(cfg)}));
  const command = pipe('huima-config.sh', base, [data]);
  return {command, preview: command.replace(data, `${data.slice(0, 6)}……（含 Key，已隐藏）`)};
}

export function buildMacRestoreCommand(base) {
  return pipe('huima-config.sh', base, ['--restore']);
}
