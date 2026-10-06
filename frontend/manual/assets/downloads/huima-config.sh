#!/bin/bash
# 汇码 · 一键配置 / 恢复配置（macOS）。Keep LF line endings.
# Configure: curl -fsSL <site>/docs/assets/downloads/huima-config.sh | bash -s -- '<base64 data from the manual page>'
# Restore:   curl -fsSL <site>/docs/assets/downloads/huima-config.sh | bash -s -- --restore
# The data (keys, models, endpoints) is passed as an argument and never sent anywhere; this script only writes local files.
# JSON is edited with macOS's built-in JavaScript (osascript), so no Node or Python is needed.
# Every file is backed up to ~/.huima/backups/<time> before it changes, in the same format as the Windows script.

if [ -t 1 ]; then C_STEP=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_END=$'\033[0m'
else C_STEP=''; C_OK=''; C_WARN=''; C_ERR=''; C_END=''; fi

ask() {
  # curl | bash feeds the script itself on stdin, so answers come from the terminal.
  local answer=''
  if [ -n "${HUIMA_ASSUME_YES:-}" ]; then printf 'Y'; return; fi
  if [ -r /dev/tty ]; then
    printf '%s' "$1" > /dev/tty
    IFS= read -r answer < /dev/tty || answer=''
  fi
  printf '%s' "$answer"
}

write_engine() {
  cat > "$1" <<'JXA'
ObjC.import('Foundation');
ObjC.import('stdlib');

// >>> pure: no ObjC below this line until "<<< pure"; frontend/tests/manual loads this part in Node.
const URL_PATTERN = /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?(\/[A-Za-z0-9._~\/-]*)?$/;
const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:\/-]{0,127}$/;
const LABELS = {claude: 'Claude Code', codex: 'Codex', workbuddy: 'WorkBuddy'};
const ROLE_VARS = [
  ['fable', 'ANTHROPIC_DEFAULT_FABLE_MODEL', 'Fable'], ['opus', 'ANTHROPIC_DEFAULT_OPUS_MODEL', 'Opus'],
  ['sonnet', 'ANTHROPIC_DEFAULT_SONNET_MODEL', 'Sonnet'], ['haiku', 'ANTHROPIC_DEFAULT_HAIKU_MODEL', 'Haiku（含后台任务）'],
  ['subagent', 'CLAUDE_CODE_SUBAGENT_MODEL', '子代理'],
];

function isObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }

function validateData(data) {
  if (!isObject(data) || !isObject(data.tools) || !isObject(data.settings)) throw new Error('配置数据不完整，请回到手册重新生成命令。');
  const s = data.settings;
  for (const url of [s.site, s.codex, s.workbuddy_url]) {
    if (typeof url !== 'string' || !URL_PATTERN.test(url)) throw new Error('接口地址格式不正确：' + url);
  }
  const names = Object.keys(data.tools).filter(name => Object.prototype.hasOwnProperty.call(LABELS, name));
  if (!names.length) throw new Error('没有要配置的软件，请回到手册重新生成命令。');
  for (const name of names) {
    const item = data.tools[name];
    if (!isObject(item) || typeof item.apiKey !== 'string' || !item.apiKey || item.apiKey.length > 2048 || /[\s\x00-\x1f\x7f-\x9f]/.test(item.apiKey)) {
      throw new Error(LABELS[name] + '：Key 不完整，请回到手册重新生成命令。');
    }
    if (typeof item.model !== 'string' || !MODEL_PATTERN.test(item.model)) throw new Error(LABELS[name] + '：模型名称不正确。');
  }
  return names;
}

// Same rules as the Windows script: keep the user's other settings, replace only what the manual owns.
function mergeClaudeSettings(settings, key, model, roles, site) {
  if (settings === null || settings === undefined) settings = {};
  if (!isObject(settings)) throw new Error('settings.json 的格式无法识别，本项未修改。');
  const env = isObject(settings.env) ? settings.env : {};
  // An API key next to the auth token makes Claude Code report an auth conflict.
  delete env.ANTHROPIC_API_KEY;
  // The main model goes to "model" so a later /model choice persists; ANTHROPIC_MODEL would override it.
  delete env.ANTHROPIC_MODEL;
  env.ANTHROPIC_BASE_URL = site;
  env.ANTHROPIC_AUTH_TOKEN = key;
  const summary = [];
  for (const [role, name, label] of ROLE_VARS) {
    const value = isObject(roles) && typeof roles[role] === 'string' ? roles[role] : '';
    if (value && MODEL_PATTERN.test(value)) { env[name] = value; summary.push(label + ' → ' + value); }
    else delete env[name];
  }
  settings.env = env;
  settings.model = model;
  return {settings, summary};
}

// Skip Claude Code's first-run sign-in screen, touching only this one flag in a possibly large state file.
function markOnboarding(text) {
  if (text === null || text === undefined) return {action: 'create', text: '{\n  "hasCompletedOnboarding": true\n}\n'};
  let state;
  try { state = JSON.parse(text); } catch (error) { return {action: 'skip'}; }
  if (!isObject(state)) return {action: 'skip'};
  if (state.hasCompletedOnboarding === true) return {action: 'done'};
  let updated;
  if (Object.prototype.hasOwnProperty.call(state, 'hasCompletedOnboarding')) {
    updated = text.replace(/"hasCompletedOnboarding"\s*:\s*false/, '"hasCompletedOnboarding": true');
  } else {
    const brace = text.indexOf('{');
    const rest = text.slice(brace + 1);
    updated = text.slice(0, brace + 1) + '"hasCompletedOnboarding": true' + (rest.trim().startsWith('}') ? '' : ',') + rest;
  }
  try { if (JSON.parse(updated).hasCompletedOnboarding === true) return {action: 'update', text: updated}; } catch (error) { /* fall through */ }
  return {action: 'skip'};
}

function mergeCodexConfig(text, model, baseUrl) {
  const lines = text ? text.split(/\r?\n/) : [];
  const kept = [];
  let inRoot = true, skipping = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('[')) {
      inRoot = false;
      skipping = /^\[\s*model_providers\s*\.\s*"?huima"?\s*\]/.test(trimmed);
      if (skipping) continue;
    }
    if (skipping) continue;
    if (inRoot && /^(model|model_provider|preferred_auth_method)\s*=/.test(trimmed)) continue;
    kept.push(line);
  }
  while (kept.length && !kept[kept.length - 1].trim()) kept.pop();
  const out = ['model_provider = "huima"', 'model = "' + model + '"', 'preferred_auth_method = "apikey"'];
  if (kept.length) out.push('', ...kept);
  out.push('', '[model_providers.huima]', 'name = "汇码"', 'base_url = "' + baseUrl + '"', 'wire_api = "responses"', 'requires_openai_auth = true', '');
  return out.join('\n');
}

function codexAuth(key) { return JSON.stringify({OPENAI_API_KEY: key}, null, 2) + '\n'; }

function workbuddyEntry(key, model, s) {
  const wb = s.workbuddy || {};
  return {
    id: model, name: model, vendor: 'Custom', url: s.workbuddy_url, apiKey: key,
    maxInputTokens: Number(wb.max_input_tokens) || 128000, maxOutputTokens: Number(wb.max_output_tokens) || 8192,
    supportsToolCall: wb.supports_tool_call !== false, supportsImages: wb.supports_images === true,
    supportsReasoning: wb.supports_reasoning === true,
  };
}

function mergeWorkbuddy(document, entry, site) {
  const isOurs = item => isObject(item) && typeof item.url === 'string' && item.url.startsWith(site);
  // WorkBuddy itself creates models.json as a top-level array on first launch, so use that shape.
  if (document === null || document === undefined) return [entry];
  if (Array.isArray(document)) return document.filter(item => !isOurs(item)).concat(entry);
  if (isObject(document) && (document.models === undefined || Array.isArray(document.models))) {
    document.models = (document.models || []).filter(item => !isOurs(item)).concat(entry);
    const available = Array.isArray(document.availableModels) ? document.availableModels : [];
    if (!available.includes(entry.id)) available.push(entry.id);
    document.availableModels = available;
    return document;
  }
  throw new Error('models.json 的格式无法识别，本项未修改。请改用 WorkBuddy 设置界面手动添加。');
}

function backupStamp(date) {
  const pad = n => String(n).padStart(2, '0');
  return date.getFullYear() + pad(date.getMonth() + 1) + pad(date.getDate()) + '-' + pad(date.getHours()) + pad(date.getMinutes()) + pad(date.getSeconds());
}

// Newest backup that has not been restored yet; names sort by time.
function pickRestore(entries) {
  const sorted = entries.slice().sort((a, b) => (a.name < b.name ? 1 : a.name > b.name ? -1 : 0));
  return sorted.find(entry => isObject(entry.manifest) && entry.manifest.status === 'active' && Array.isArray(entry.manifest.files)) || null;
}
// <<< pure

const fm = $.NSFileManager.defaultManager;
const HOME = ObjC.unwrap($.NSHomeDirectory());
const BACKUP_ROOT = HOME + '/.huima/backups';

function say(text) { console.log(text); }
function env(name) {
  const value = $.NSProcessInfo.processInfo.environment.objectForKey(name);
  return value.isNil() ? '' : ObjC.unwrap(value);
}
function exists(path) { return fm.fileExistsAtPath(path); }
function dirname(path) { return path.replace(/\/[^\/]*$/, '') || '/'; }
function mkdirp(dir) { fm.createDirectoryAtPathWithIntermediateDirectoriesAttributesError(dir, true, $(), null); }
function readText(path) {
  if (!exists(path)) return null;
  const value = $.NSString.stringWithContentsOfFileEncodingError(path, $.NSUTF8StringEncoding, null);
  if (value.isNil()) throw new Error(path + ' 无法按 UTF-8 读取，本项未修改。');
  const text = ObjC.unwrap(value);
  return text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text;
}
function readJson(path) {
  const text = readText(path);
  if (text === null || !text.trim()) return null;
  try { return JSON.parse(text); } catch (error) { throw new Error(path + ' 不是有效的 JSON。为避免损坏原有配置，本项未修改，请联系客服。'); }
}
function writeText(path, text) {
  mkdirp(dirname(path));
  // atomically: writes a temporary file and renames it, so a crash never leaves half a file.
  if (!$(text).writeToFileAtomicallyEncodingError(path, true, $.NSUTF8StringEncoding, null)) throw new Error('无法写入 ' + path);
}
function copyFile(from, to) {
  if (exists(to)) fm.removeItemAtPathError(to, null);
  if (!fm.copyItemAtPathToPathError(from, to, null)) throw new Error('无法复制 ' + from);
}
function removeFile(path) { if (exists(path)) fm.removeItemAtPathError(path, null); }
function listDir(path) {
  const items = fm.contentsOfDirectoryAtPathError(path, null);
  return items.isNil() ? [] : ObjC.deepUnwrap(items);
}
function decodeData(b64) {
  const data = $.NSData.alloc.initWithBase64EncodedStringOptions(b64, 0);
  if (data.isNil()) throw new Error('配置数据不完整（可能没有复制全），请回到手册重新复制命令。');
  const text = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding);
  if (text.isNil()) throw new Error('配置数据无法识别，请回到手册重新复制命令。');
  try { return JSON.parse(ObjC.unwrap(text)); } catch (error) { throw new Error('配置数据无法识别，请回到手册重新复制命令。'); }
}

let backupDir = null;
const entries = [];
function saveManifest(status) {
  writeText(backupDir + '/manifest.json', JSON.stringify({version: 1, created: new Date().toISOString(), status, files: entries}, null, 2));
}
function backup(path) {
  if (entries.some(entry => entry.path === path)) return;
  if (!backupDir) {
    let name = backupStamp(new Date()), n = 1;
    while (exists(BACKUP_ROOT + '/' + name)) name = backupStamp(new Date()) + '-' + (++n);
    backupDir = BACKUP_ROOT + '/' + name;
    mkdirp(backupDir);
  }
  const existed = exists(path);
  let copy = null;
  if (existed) { copy = 'file' + entries.length + '.bak'; copyFile(path, backupDir + '/' + copy); }
  entries.push({path, existed, copy});
  saveManifest('active');
}

function configureClaude(item, s) {
  say('\n配置 Claude Code');
  const path = HOME + '/.claude/settings.json';
  const result = mergeClaudeSettings(readJson(path), item.apiKey, item.model, item.roles, s.site);
  backup(path);
  writeText(path, JSON.stringify(result.settings, null, 2) + '\n');
  say('  [完成] 已写入 ' + path + '，主模型 ' + item.model);
  result.summary.forEach(line => say('         ' + line));
  const statePath = HOME + '/.claude.json';
  const onboarding = markOnboarding(readText(statePath));
  if (onboarding.action === 'create' || onboarding.action === 'update') {
    backup(statePath);
    writeText(statePath, onboarding.text);
    say('  [完成] 已跳过首次登录引导');
  } else if (onboarding.action === 'done') say('  [完成] 首次登录引导此前已完成');
  else say('  [注意] .claude.json 结构特殊，未修改。首次打开若出现登录页，请联系客服。');
}

function configureCodex(item, s) {
  say('\n配置 Codex（桌面版和命令行版共用）');
  let root = HOME + '/.codex';
  const custom = env('CODEX_HOME');
  if (custom) { root = custom; say('  [注意] 检测到 CODEX_HOME，配置写入 ' + root); }
  const configPath = root + '/config.toml';
  const text = mergeCodexConfig(readText(configPath), item.model, s.codex);
  backup(configPath);
  writeText(configPath, text);
  say('  [完成] 已写入 ' + configPath + '，模型 ' + item.model);
  const authPath = root + '/auth.json';
  backup(authPath);
  writeText(authPath, codexAuth(item.apiKey));
  say('  [完成] 已写入 ' + authPath + '（原有登录已备份）');
}

function configureWorkbuddy(item, s) {
  say('\n配置 WorkBuddy');
  const path = HOME + '/.workbuddy/models.json';
  const document = mergeWorkbuddy(readJson(path), workbuddyEntry(item.apiKey, item.model, s), s.site);
  backup(path);
  writeText(path, JSON.stringify(document, null, 2) + '\n');
  say('  [完成] 已写入 ' + path + '，模型 ' + item.model);
}

function describe(b64) {
  const data = decodeData(b64);
  const names = validateData(data);
  say('将配置：' + names.map(name => LABELS[name]).join('、'));
  say('接口地址：' + data.settings.site);
  return 0;
}

function apply(b64) {
  const data = decodeData(b64);
  const names = validateData(data);
  const failed = [];
  for (const name of names) {
    try {
      if (name === 'claude') configureClaude(data.tools.claude, data.settings);
      if (name === 'codex') configureCodex(data.tools.codex, data.settings);
      if (name === 'workbuddy') configureWorkbuddy(data.tools.workbuddy, data.settings);
    } catch (error) {
      failed.push(LABELS[name]);
      say('  [失败] ' + error.message);
    }
  }
  say('');
  if (backupDir) say('备份位置：' + backupDir);
  if (failed.length) { say('未完成：' + failed.join('、') + '。其他软件已配置好，可以先使用。'); return 1; }
  return 0;
}

function latestBackup() {
  if (!exists(BACKUP_ROOT)) return null;
  const list = listDir(BACKUP_ROOT).map(name => {
    let manifest = null;
    try { manifest = readJson(BACKUP_ROOT + '/' + name + '/manifest.json'); } catch (error) { manifest = null; }
    return {name, manifest};
  });
  return pickRestore(list);
}

function restorePlan() {
  if (!exists(BACKUP_ROOT)) { say('没有找到汇码配置脚本留下的备份，无需恢复。'); return 2; }
  const latest = latestBackup();
  if (!latest) { say('所有备份都已恢复过，没有需要恢复的内容。'); return 2; }
  say('将恢复到这次配置之前的状态：' + BACKUP_ROOT + '/' + latest.name);
  latest.manifest.files.forEach(file => say(file.existed ? '  还原 ' + file.path : '  删除（配置前不存在）' + file.path));
  return 0;
}

function restoreApply() {
  const latest = latestBackup();
  if (!latest) { say('没有需要恢复的内容。'); return 0; }
  const dir = BACKUP_ROOT + '/' + latest.name;
  for (const file of latest.manifest.files) {
    if (file.existed) { mkdirp(dirname(file.path)); copyFile(dir + '/' + file.copy, file.path); }
    else removeFile(file.path);
  }
  latest.manifest.status = 'restored';
  writeText(dir + '/manifest.json', JSON.stringify(latest.manifest, null, 2));
  return 0;
}

function run(argv) {
  let code = 1;
  try {
    const mode = argv[0];
    if (mode === 'describe') code = describe(argv[1]);
    else if (mode === 'apply') code = apply(argv[1]);
    else if (mode === 'restore-plan') code = restorePlan();
    else if (mode === 'restore-apply') code = restoreApply();
    else throw new Error('不支持的参数。');
  } catch (error) {
    say('停止：' + error.message);
    code = 1;
  }
  $.exit(code);
}
JXA
}

check_env_conflicts() {
  local names="$1" name file
  for name in $names; do
    if [ -n "$(launchctl getenv "$name" 2>/dev/null)" ]; then
      printf '  %s[注意] 系统环境变量里还有 %s，可能与本配置冲突。不确定时请联系客服，不要随意删除。%s\n' "$C_WARN" "$name" "$C_END"
    fi
    for file in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.zshenv" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do
      if [ -f "$file" ] && grep -Eq "^[[:space:]]*(export[[:space:]]+)?$name=" "$file"; then
        printf '  %s[注意] %s 里设置了 %s，可能与本配置冲突。不确定时请联系客服，不要随意删除。%s\n' "$C_WARN" "$file" "$name" "$C_END"
      fi
    done
  done
}

main() {
  local tmp engine code
  echo '========================================================'
  if [ "${1:-}" = --restore ]; then echo '               汇码 · 恢复配置（Mac）'; else echo '               汇码 · 一键配置（Mac）'; fi
  echo '========================================================'
  if [ "$(uname -s)" != Darwin ]; then echo '这个脚本只能在 Mac 上运行。Windows 请回到手册下载 .cmd 脚本。'; return 1; fi
  if [ -z "${1:-}" ]; then echo '缺少配置数据。请回到手册的“4.2 一键配置”，生成并复制完整命令。'; return 1; fi
  # BSD mktemp cannot add a suffix, so give the engine a .js name inside a private temporary folder.
  tmp=$(mktemp -d -t huima-config) || return 1
  # Expand now: $tmp is local and gone by the time the EXIT trap runs.
  trap "rm -rf '$tmp'" EXIT
  engine="$tmp/engine.js"
  write_engine "$engine"

  if [ "$1" = --restore ]; then
    osascript -l JavaScript "$engine" restore-plan
    code=$?
    [ "$code" = 2 ] && return 0
    [ "$code" = 0 ] || return "$code"
    printf '\n%s请先关闭 Claude Code、Codex 和 WorkBuddy 窗口。%s\n' "$C_WARN" "$C_END"
    case "$(ask '输入 Y 并回车开始恢复（其他内容取消）：')" in
      Y|y) ;;
      *) echo '已取消，没有修改任何文件。'; return 0 ;;
    esac
    osascript -l JavaScript "$engine" restore-apply || return 1
    printf '%s恢复完成。重新打开软件即可回到之前的状态。%s\n' "$C_OK" "$C_END"
    echo '再运行一次同一行恢复命令，可以继续恢复更早的一次配置。'
    return 0
  fi

  osascript -l JavaScript "$engine" describe "$1" || return 1
  echo '改动前会自动备份原文件，之后可用手册里的“恢复命令”一键还原。'
  printf '\n%s请先关闭 Claude Code、Codex 和 WorkBuddy 窗口，再继续。%s\n' "$C_WARN" "$C_END"
  case "$(ask '准备好后输入 Y 并回车（其他内容取消）：')" in
    Y|y) ;;
    *) echo '已取消，没有修改任何文件。'; return 0 ;;
  esac
  osascript -l JavaScript "$engine" apply "$1"
  code=$?
  # Files holding a key are readable only by this user.
  chmod 600 "$HOME/.claude/settings.json" "${CODEX_HOME:-$HOME/.codex}/auth.json" "$HOME/.workbuddy/models.json" 2>/dev/null
  chmod -R go-rwx "$HOME/.huima/backups" 2>/dev/null
  check_env_conflicts 'ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL OPENAI_API_KEY OPENAI_BASE_URL'
  echo
  if [ "$code" = 0 ]; then
    printf '%s配置完成！打开软件，按手册“第 5 步”发一条消息测试。%s\n' "$C_OK" "$C_END"
  fi
  echo '刚才的命令里有你的 API Key：不要把终端截图或这条命令发给别人。'
  return "$code"
}

main "$@"
