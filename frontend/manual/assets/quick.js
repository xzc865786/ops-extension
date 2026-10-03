import {newestMatch, parseAvailableModels, validateApiKey} from './ccswitch-setup-core.js';
import {fillRoleSelects, readRoleSelects, resetRoleSelects} from './claude-roles.js';
import {TOOLS, buildConfigCmd, buildRollbackCmd} from './quick-config-core.js';

const byId = id => document.getElementById(id);
const toolNames = Object.keys(TOOLS);
const installBoxes = Array.from(document.querySelectorAll('input[name="install-tool"]'));
const configBoxes = Array.from(document.querySelectorAll('input[name="config-tool"]'));
const sharedKey = byId('quick-key');
const loadButton = byId('load-models');
const consent = byId('config-consent');
let configTouched = false;
let lookup = null;
let claudeIds = [];

// Preselect a sensible default so beginners only need to confirm.
const PREFERRED = {
  claude: [/sonnet/i, /opus/i],
  codex: [/codex/i, /^gpt-5/i],
  workbuddy: [/sonnet/i, /^gpt-5/i, /deepseek/i],
};

function status(id, message, error = false) {
  const element = byId(id);
  element.textContent = message;
  element.classList.toggle('error', error);
}

function download(text, name) {
  const url = URL.createObjectURL(new Blob([text], {type: 'application/octet-stream'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function checked(boxes) {
  return boxes.filter(box => box.checked).map(box => box.value);
}

function overrideKey(tool) {
  return byId(`key-${tool}`).value;
}

function resetModels(tool, message = '先粘贴 Key，再点击“读取可用模型”') {
  const select = byId(`model-${tool}`);
  select.replaceChildren(new Option(message, ''));
  select.disabled = true;
  status(`status-${tool}`, '');
  if (tool === 'claude') resetRoleSelects('role-claude-');
}

function resetAll() {
  lookup?.abort();
  lookup = null;
  toolNames.forEach(tool => resetModels(tool));
  consent.checked = false;
  loadButton.disabled = false;
  loadButton.textContent = '读取可用模型';
}

function syncToolBlocks() {
  for (const tool of toolNames) byId(`tool-${tool}`).hidden = !configBoxes.find(box => box.value === tool).checked;
}

// --- Step 2: install script -------------------------------------------------
installBoxes.forEach(box => box.addEventListener('change', () => {
  if (configTouched) return;
  configBoxes.find(item => item.value === box.value).checked = box.checked;
  syncToolBlocks();
}));

byId('download-install').addEventListener('click', async () => {
  const tools = checked(installBoxes);
  if (!tools.length) {
    status('install-status', '请至少勾选一个要安装的软件。', true);
    return;
  }
  try {
    const response = await fetch('assets/downloads/huima-install.cmd', {cache: 'no-store'});
    if (!response.ok) throw new Error();
    const template = await response.text();
    const script = template.replace(/^set "HUIMA_TOOLS=[^"\r\n]*"/m, `set "HUIMA_TOOLS=${tools.join(',')}"`);
    if (script === template) throw new Error();
    download(script, 'huima-install.cmd');
    status('install-status', '安装脚本已开始下载。在浏览器的下载列表里找到 huima-install.cmd，双击运行。');
  } catch {
    status('install-status', '生成失败，已改为下载通用版：运行后按窗口提示输入编号选择软件。', true);
    window.location.href = 'assets/downloads/huima-install.cmd';
  }
});

// --- Step 3: configuration script -------------------------------------------
configBoxes.forEach(box => box.addEventListener('change', () => {
  configTouched = true;
  syncToolBlocks();
}));
syncToolBlocks();

// The main model is the fallback for roles the group lacks, so refresh the suggestions when it changes.
byId('model-claude').addEventListener('change', event => {
  if (event.target.value) fillRoleSelects('role-claude-', claudeIds, event.target.value);
});

sharedKey.addEventListener('input', resetAll);
toolNames.forEach(tool => byId(`key-${tool}`).addEventListener('input', () => {
  resetModels(tool, '这把 Key 改过了，请重新读取模型');
  consent.checked = false;
}));

async function fetchModels(key, signal) {
  const response = await fetch('/v1/models', {
    method: 'GET',
    headers: {Authorization: `Bearer ${key}`, Accept: 'application/json'},
    credentials: 'omit', cache: 'no-store', redirect: 'error', signal,
  });
  if (response.status === 401) throw new Error('Key 无效或已失效，请从后台重新复制。');
  if (response.status === 403) throw new Error('这把 Key 无权读取模型，请检查分组和状态。');
  if (!response.ok) throw new Error(`模型读取失败（HTTP ${response.status}），请稍后重试。`);
  return response.json().catch(() => { throw new Error('模型接口返回格式不正确，请稍后重试。'); });
}

function fillModels(tool, payload) {
  const models = parseAvailableModels(payload, TOOLS[tool].platform);
  const select = byId(`model-${tool}`);
  if (!models.length) {
    resetModels(tool, '这把 Key 没有可用于该软件的模型');
    status(`status-${tool}`, `这把 Key 的分组不支持 ${TOOLS[tool].label}。展开下方“用另一把 Key”，填写支持它的 Key 后重新读取。`, true);
    return false;
  }
  const ids = models.map(model => model.id);
  let preferred = ids[0];
  for (const pattern of PREFERRED[tool]) {
    const match = newestMatch(ids, pattern);
    if (match) { preferred = match; break; }
  }
  select.replaceChildren(...models.map(({id, label}) => {
    const option = new Option(id === preferred ? `${label}（推荐）` : label, id);
    option.selected = id === preferred;
    return option;
  }));
  select.disabled = false;
  if (tool === 'claude') { claudeIds = ids; fillRoleSelects('role-claude-', ids, preferred); }
  status(`status-${tool}`, `可用模型 ${models.length} 个，已选好推荐模型，也可以自己换。`);
  return true;
}

loadButton.addEventListener('click', async () => {
  const tools = checked(configBoxes);
  if (!tools.length) {
    status('config-status', '请至少勾选一个要配置的软件。', true);
    return;
  }
  const keys = new Map();
  try {
    for (const tool of tools) {
      const key = overrideKey(tool) || sharedKey.value;
      validateApiKey(key);
      if (!keys.has(key)) keys.set(key, []);
      keys.get(key).push(tool);
    }
  } catch (error) {
    status('config-status', error.message, true);
    return;
  }
  lookup?.abort();
  const controller = new AbortController();
  lookup = controller;
  loadButton.disabled = true;
  loadButton.textContent = '读取中...';
  tools.forEach(tool => resetModels(tool, '正在读取模型...'));
  status('config-status', '正在读取这把 Key 可用的模型...');
  let ok = 0;
  try {
    for (const [key, group] of keys) {
      try {
        const payload = await fetchModels(key, controller.signal);
        if (lookup !== controller) return;
        group.forEach(tool => { if (fillModels(tool, payload)) ok += 1; });
      } catch (error) {
        if (controller.signal.aborted) return;
        const message = error instanceof TypeError ? '无法连接模型接口，请稍后重试。' : error.message;
        group.forEach(tool => { resetModels(tool, '读取失败'); status(`status-${tool}`, message, true); });
      }
    }
    status('config-status', ok === tools.length ? '模型已读取，核对后勾选下方确认，再下载配置脚本。'
      : '部分软件没有读到模型，请看对应软件下方的提示。', ok !== tools.length);
  } finally {
    if (lookup === controller) {
      lookup = null;
      loadButton.disabled = false;
      loadButton.textContent = '读取可用模型';
    }
  }
});

byId('download-config').addEventListener('click', () => {
  try {
    const tools = checked(configBoxes);
    if (!tools.length) throw new Error('请至少勾选一个要配置的软件。');
    const input = {};
    for (const tool of tools) {
      const model = byId(`model-${tool}`).value;
      if (!model) throw new Error(`请先读取 ${TOOLS[tool].label} 的可用模型。`);
      input[tool] = {apiKey: overrideKey(tool) || sharedKey.value, model};
      if (tool === 'claude') input.claude.roles = readRoleSelects('role-claude-');
    }
    if (!consent.checked) throw new Error('请先勾选确认：配置脚本里有你的 Key。');
    download(buildConfigCmd(input), 'huima-config.cmd');
    sharedKey.value = '';
    toolNames.forEach(tool => { byId(`key-${tool}`).value = ''; });
    resetAll();
    status('config-status', '配置脚本已开始下载，页面上的 Key 已清空。在下载列表里双击 huima-config.cmd 运行。');
  } catch (error) {
    status('config-status', error.message, true);
  }
});

byId('clear-config').addEventListener('click', () => {
  sharedKey.value = '';
  toolNames.forEach(tool => { byId(`key-${tool}`).value = ''; });
  resetAll();
  status('config-status', '页面上的 Key 已清空。已经下载的脚本不会被删除。');
});

byId('download-rollback').addEventListener('click', () => {
  download(buildRollbackCmd(), 'huima-restore.cmd');
  status('rollback-status', '恢复脚本已开始下载。双击运行，按提示输入 Y 即可。');
});

resetAll();
window.addEventListener('pagehide', () => { sharedKey.value = ''; toolNames.forEach(tool => { byId(`key-${tool}`).value = ''; }); resetAll(); });
window.addEventListener('pageshow', event => { if (event.persisted) resetAll(); });
