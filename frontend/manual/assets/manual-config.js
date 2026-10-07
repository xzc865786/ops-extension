// Loads the manual configuration (admin-editable in the Ops console) and fills it into the page.
// Falls back to the bundled defaults when the API is unreachable or returns something unsafe,
// so the manual always works. Values feed scripts that run on users' PCs, hence the re-validation.
import {derive, isSafeConfig, isSafeGroups} from './manual-config-core.js';

const API_URL = '/ext/api/v1/public/manual-config';
const DEFAULT_URL = 'assets/manual-config.default.json';

const HTTPS_URL = /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?(\/[A-Za-z0-9._~/-]*)?$/;

async function fetchJson(url) {
  const response = await fetch(url, {credentials: 'omit', redirect: 'error'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function load() {
  try {
    const payload = await fetchJson(API_URL);
    if (isSafeConfig(payload?.config)) {
      const config = payload.config;
      // The group page is text only and never reaches scripts; a bad copy of it only replaces itself.
      if (!isSafeGroups(config.groups)) config.groups = (await fetchJson(DEFAULT_URL).catch(() => null))?.groups ?? null;
      return {config, version: payload.version, source: 'api'};
    }
  } catch { /* Fall through to the bundled defaults. */ }
  const config = await fetchJson(DEFAULT_URL);
  return {config, version: 0, source: 'default'};
}

function formatDate(isoDate) {
  const [year, month, day] = String(isoDate).split('-').map(Number);
  return year && month && day ? `${year} 年 ${month} 月 ${day} 日` : '';
}

function lookup(cfg, path) {
  const extra = derive(cfg);
  const virtual = {
    'site.url': extra.site, 'site.host': extra.host,
    'endpoint.claude': extra.endpoints.claude, 'endpoint.codex': extra.endpoints.codex,
    'endpoint.workbuddy': extra.endpoints.workbuddy, 'updated_on': formatDate(cfg.updated_on),
  };
  if (path in virtual) return virtual[path];
  return path.split('.').reduce((value, key) => (value == null ? undefined : value[key]), cfg);
}

function applyBindings(cfg) {
  const {site, ccswitchDownload} = derive(cfg);
  for (const element of document.querySelectorAll('[data-cfg]')) {
    const value = lookup(cfg, element.dataset.cfg);
    if (value !== undefined && value !== null && value !== '') element.textContent = String(value);
    const block = element.closest('[data-cfg-block]');
    if (block) block.hidden = value === '' || value === undefined;
  }
  for (const link of document.querySelectorAll('[data-cfg-href]')) {
    const path = link.dataset.cfgHref;
    link.href = path === '/' ? site : `${site}${path}`;
    if (link.hasAttribute('data-cfg-text')) link.textContent = link.href;
  }
  for (const link of document.querySelectorAll('[data-cfg-download="ccswitch-windows"]')) {
    link.href = ccswitchDownload;
  }
  for (const link of document.querySelectorAll('[data-cfg-link]')) {
    const value = lookup(cfg, link.dataset.cfgLink);
    if (typeof value === 'string' && HTTPS_URL.test(value)) link.href = value;
  }
  const announcement = cfg.announcement;
  const main = document.getElementById('main-content');
  if (announcement.enabled && announcement.text && main && !document.querySelector('.manual-announcement')) {
    const banner = document.createElement('div');
    banner.className = `notice manual-announcement${announcement.level === 'warning' ? ' warning' : ''}`;
    banner.setAttribute('role', 'status');
    const label = document.createElement('strong');
    label.textContent = '公告：';
    banner.append(label, document.createTextNode(announcement.text));
    const status = document.getElementById('search-status');
    if (status) status.after(banner); else main.prepend(banner);
  }
}

export const manualConfigReady = load().then(result => {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => applyBindings(result.config), {once: true});
  } else {
    applyBindings(result.config);
  }
  document.documentElement.dataset.manualConfig = `${result.source}:${result.version}`;
  return result.config;
});
