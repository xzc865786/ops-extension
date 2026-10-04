import {buildImportUrl, getTargetDetails, parseAvailableModels, recommendModel, validateApiKey, validateImportInput} from './ccswitch-setup-core.js';
import {fillRoleSelects, readRoleSelects, resetRoleSelects} from './claude-roles.js';
import {download, guardClick} from './ui.js';
import {buildRollbackCmd} from './codex-setup-core.js';

const byId = id => document.getElementById(id);
const targets = Array.from(document.querySelectorAll('input[name="import-target"]'));
const nameInput = byId('import-name');
const keyInput = byId('import-key');
const modelSelect = byId('import-model');
const loadButton = byId('import-load');
let previousAutoName = '汇码 - Claude Code';
let lookup = null;
let lastModelIds = [];

// Role suggestions depend on the main model (it is the fallback for roles the group lacks).
modelSelect.addEventListener('change', () => {
  if (selectedTarget() === 'claude' && modelSelect.value) fillRoleSelects('import-role-', lastModelIds, modelSelect.value);
});

function status(id, message, error = false) {
  const element = byId(id);
  element.textContent = message;
  element.classList.toggle('error', error);
}

function selectedTarget() {
  return targets.find(input => input.checked)?.value || 'claude';
}

function resetModels(message = '先粘贴 Key，再点击“读取可用模型”') {
  lookup?.abort();
  lookup = null;
  modelSelect.replaceChildren(new Option(message, ''));
  modelSelect.disabled = true;
  loadButton.disabled = false;
  loadButton.textContent = '读取可用模型';
  resetRoleSelects('import-role-');
}

function updateTarget() {
  const target = selectedTarget();
  const details = getTargetDetails(target);
  const autoName = `汇码 - ${details.label}`;
  if (nameInput.value === previousAutoName || !nameInput.value.trim()) nameInput.value = autoName;
  previousAutoName = autoName;
  byId('import-app').textContent = details.label;
  byId('import-endpoint').textContent = details.endpoint;
  byId('import-protocol').textContent = target === 'codex' ? 'Responses' : 'Anthropic';
  byId('import-roles').hidden = target !== 'claude';
  resetModels();
  status('import-status', '粘贴 Key 后点击“读取可用模型”。');
}

targets.forEach(input => input.addEventListener('change', updateTarget));
keyInput.addEventListener('input', () => { resetModels(); status('import-status', 'Key 已改变，请重新读取模型。'); });
updateTarget();

loadButton.addEventListener('click', async () => {
  let key;
  try { key = validateApiKey(keyInput.value); }
  catch (error) { status('import-status', error.message, true); return; }
  const target = selectedTarget();
  resetModels('正在读取模型...');
  const controller = new AbortController();
  lookup = controller;
  loadButton.disabled = true;
  loadButton.textContent = '读取中...';
  try {
    const response = await fetch('/v1/models', {
      method: 'GET',
      headers: {Authorization: `Bearer ${key}`, Accept: 'application/json'},
      credentials: 'omit', cache: 'no-store', redirect: 'error', signal: controller.signal,
    });
    if (response.status === 401) throw new Error('Key 无效或已失效，请从后台重新复制。');
    if (response.status === 403) throw new Error('这把 Key 无权读取模型，请检查分组和状态。');
    if (!response.ok) throw new Error(`模型读取失败（HTTP ${response.status}），请稍后重试。`);
    const payload = await response.json().catch(() => { throw new Error('模型接口返回格式不正确，请稍后重试。'); });
    const models = parseAvailableModels(payload, getTargetDetails(target).platform);
    if (!models.length) throw new Error(`这把 Key 没有可用于 ${getTargetDetails(target).label} 的模型，请检查分组。`);
    if (lookup !== controller || keyInput.value !== key || selectedTarget() !== target) return;
    lastModelIds = models.map(model => model.id);
    // Codex gets a default (gpt-6.1-sol, else gpt-6-luna); Claude Code users pick their own main model.
    const preferred = target === 'codex' ? recommendModel(lastModelIds, 'codex') : '';
    modelSelect.replaceChildren(new Option('请选择模型', ''), ...models.map(({id, label}) =>
      new Option(id === preferred ? `${label}（推荐）` : label, id, false, id === preferred)));
    modelSelect.disabled = false;
    status('import-status', `已读取 ${models.length} 个可用模型，请选择。`);
  } catch (error) {
    if (controller.signal.aborted || lookup !== controller) return;
    modelSelect.replaceChildren(new Option('读取失败，请重试', ''));
    status('import-status', error instanceof TypeError ? '无法连接模型接口，请稍后重试。' : error.message, true);
  } finally {
    if (lookup === controller) {
      lookup = null;
      loadButton.disabled = false;
      loadButton.textContent = '读取可用模型';
    }
  }
});

guardClick(byId('import-open'), () => {
  try {
    if (!modelSelect.value) throw new Error('请先读取并选择模型。');
    const url = buildImportUrl(validateImportInput({
      target: selectedTarget(), name: nameInput.value, apiKey: keyInput.value, model: modelSelect.value,
      roles: selectedTarget() === 'claude' ? readRoleSelects('import-role-') : {},
    }));
    // The browser hands the link to the installed CC Switch; nothing is sent to a server.
    window.location.href = url;
    status('import-status', '已请求打开 CC Switch。浏览器询问时选择“打开”，再在 CC Switch 里核对并确认导入。');
  } catch (error) {
    status('import-status', error.message, true);
    return false;
  }
});

byId('import-clear').addEventListener('click', () => {
  keyInput.value = '';
  resetModels();
  status('import-status', '页面上的 Key 已清空。');
});

guardClick(byId('download-legacy-rollback'), () => {
  download(buildRollbackCmd(), 'huima-codex-legacy-rollback.cmd');
  status('legacy-status', '旧版回滚脚本已开始下载。');
});

window.addEventListener('pagehide', () => { keyInput.value = ''; resetModels(); });
