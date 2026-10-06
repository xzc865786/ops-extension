/* One-click client configuration for beginners (Windows). Secrets are data, never code. */
// Every file is backed up to %USERPROFILE%\.huima\backups\<time> before it is changed;
// the rollback CMD restores the most recent active backup.

import {validateClaudeRoles} from './ccswitch-setup-core.js';
import {derive, isSafeConfig} from './manual-config-core.js';

const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;
export const TOOLS = Object.freeze({
  claude: {label: 'Claude Code'},
  codex: {label: 'Codex'},
  // WorkBuddy only speaks the OpenAI-compatible protocol, so it takes OpenAI-style keys and GPT models.
  // Non-GPT models are filtered out for now; revisit parseAvailableModels when domestic models are added.
  workbuddy: {label: 'WorkBuddy'},
});

export function validateConfigInput(input = {}) {
  const tools = {};
  for (const [name, value] of Object.entries(input)) {
    if (!Object.hasOwn(TOOLS, name) || !value) continue;
    const {apiKey, model} = value;
    if (typeof apiKey !== 'string' || !apiKey || apiKey.length > 2048 || /[\s\x00-\x1f\x7f-\x9f]/u.test(apiKey)) {
      throw new Error(`${TOOLS[name].label}：请粘贴完整 API Key，不能包含空格或换行。`);
    }
    if (typeof model !== 'string' || !MODEL_PATTERN.test(model)) throw new Error(`${TOOLS[name].label}：请选择模型。`);
    tools[name] = name === 'claude' ? {apiKey, model, roles: validateClaudeRoles(value.roles)} : {apiKey, model};
  }
  if (!Object.keys(tools).length) throw new Error('请至少选择一个要配置的软件。');
  return tools;
}

export function base64Utf8(value) {
  let binary = '';
  for (const byte of new TextEncoder().encode(value)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

// Shared helpers: JSON IO, atomic writes and the backup manifest.
const CORE = String.raw`
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$script:Utf8 = New-Object System.Text.UTF8Encoding($false)
$script:UserHome = [Environment]::GetFolderPath('UserProfile')
if ([string]::IsNullOrWhiteSpace($script:UserHome)) { throw '无法定位当前用户目录。' }
$script:BackupRoot = [IO.Path]::Combine($script:UserHome, '.huima', 'backups')

function Write-Step([string]$Message) { Write-Host ''; Write-Host $Message -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host ('  [完成] ' + $Message) -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host ('  [注意] ' + $Message) -ForegroundColor Yellow }

function Read-Text([string]$Path) {
  $text = [IO.File]::ReadAllText($Path, $script:Utf8)
  if ($text.Length -gt 0 -and $text[0] -eq [char]0xFEFF) { $text = $text.Substring(1) }
  return $text
}
function Read-JsonFile([string]$Path) {
  if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  $text = Read-Text $Path
  if ([string]::IsNullOrWhiteSpace($text)) { return $null }
  # The leading comma stops PowerShell from unrolling a top-level JSON array on return.
  try { return ,(ConvertFrom-Json -InputObject $text) }
  catch { throw ($Path + ' 不是有效的 JSON。为避免损坏原有配置，本项未修改，请联系客服。') }
}
function Write-TextFile([string]$Path, [string]$Text) {
  [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
  $temp = $Path + '.huima-tmp'
  [IO.File]::WriteAllText($temp, $Text, $script:Utf8)
  Move-Item -LiteralPath $temp -Destination $Path -Force
}
function Set-Field($Object, [string]$Name, $Value) {
  if ($Object.PSObject.Properties[$Name]) { $Object.$Name = $Value }
  else { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value }
}
function Test-JsonObject($Value) { return ($Value -is [System.Management.Automation.PSCustomObject]) }
`;

const CONFIGURE = String.raw`
$script:Backup = $null
$script:Entries = New-Object System.Collections.Generic.List[object]

function Save-Manifest([string]$Status) {
  $manifest = [ordered]@{ version = 1; created = (Get-Date).ToString('o'); status = $Status; files = $script:Entries.ToArray() }
  [IO.File]::WriteAllText([IO.Path]::Combine($script:Backup, 'manifest.json'), (ConvertTo-Json -InputObject $manifest -Depth 5), $script:Utf8)
}
function Backup-File([string]$Path) {
  foreach ($entry in $script:Entries) { if ($entry.path -eq $Path) { return } }
  if (!$script:Backup) {
    $script:Backup = [IO.Path]::Combine($script:BackupRoot, (Get-Date -Format 'yyyyMMdd-HHmmss'))
    [IO.Directory]::CreateDirectory($script:Backup) | Out-Null
  }
  $existed = Test-Path -LiteralPath $Path -PathType Leaf
  $copy = $null
  if ($existed) {
    $copy = 'file' + $script:Entries.Count + '.bak'
    Copy-Item -LiteralPath $Path -Destination ([IO.Path]::Combine($script:Backup, $copy)) -Force
  }
  $script:Entries.Add([pscustomobject][ordered]@{ path = $Path; existed = $existed; copy = $copy })
  Save-Manifest 'active'
}

function Set-ClaudeCode([string]$Key, [string]$Model, $Roles) {
  Write-Step '配置 Claude Code'
  $settingsPath = [IO.Path]::Combine($script:UserHome, '.claude', 'settings.json')
  $settings = Read-JsonFile $settingsPath
  if ($null -eq $settings) { $settings = [pscustomobject]@{} }
  if (!(Test-JsonObject $settings)) { throw 'settings.json 的格式无法识别，本项未修改。' }
  $envBlock = $null
  if ($settings.PSObject.Properties['env']) { $envBlock = $settings.env }
  if (!(Test-JsonObject $envBlock)) { $envBlock = [pscustomobject]@{} }
  # An API key next to the auth token makes Claude Code report an auth conflict.
  if ($envBlock.PSObject.Properties['ANTHROPIC_API_KEY']) { $envBlock.PSObject.Properties.Remove('ANTHROPIC_API_KEY') }
  # The main model goes to the "model" setting so a later /model choice persists; ANTHROPIC_MODEL would override it.
  if ($envBlock.PSObject.Properties['ANTHROPIC_MODEL']) { $envBlock.PSObject.Properties.Remove('ANTHROPIC_MODEL') }
  Set-Field $envBlock 'ANTHROPIC_BASE_URL' $script:Settings.site
  Set-Field $envBlock 'ANTHROPIC_AUTH_TOKEN' $Key
  $roleVars = [ordered]@{
    fable = 'ANTHROPIC_DEFAULT_FABLE_MODEL'; opus = 'ANTHROPIC_DEFAULT_OPUS_MODEL'
    sonnet = 'ANTHROPIC_DEFAULT_SONNET_MODEL'; haiku = 'ANTHROPIC_DEFAULT_HAIKU_MODEL'
    subagent = 'CLAUDE_CODE_SUBAGENT_MODEL'
  }
  $roleNames = @{ fable = 'Fable'; opus = 'Opus'; sonnet = 'Sonnet'; haiku = 'Haiku（含后台任务）'; subagent = '子代理' }
  $summary = New-Object System.Collections.Generic.List[string]
  foreach ($role in $roleVars.Keys) {
    $value = ''
    if ($null -ne $Roles -and $Roles.PSObject.Properties[$role]) { $value = [string]$Roles.$role }
    $name = $roleVars[$role]
    if ($value) { Set-Field $envBlock $name $value; $summary.Add($roleNames[$role] + ' → ' + $value) }
    elseif ($envBlock.PSObject.Properties[$name]) { $envBlock.PSObject.Properties.Remove($name) }
  }
  Set-Field $settings 'env' $envBlock
  Set-Field $settings 'model' $Model
  Backup-File $settingsPath
  Write-TextFile $settingsPath (ConvertTo-Json -InputObject $settings -Depth 32)
  Write-Ok ('已写入 ' + $settingsPath + '，主模型 ' + $Model)
  foreach ($line in $summary) { Write-Host ('         ' + $line) }

  # Skip the first-run sign-in screen. Edit only this one flag; the state file can be large.
  $statePath = [IO.Path]::Combine($script:UserHome, '.claude.json')
  if (!(Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Backup-File $statePath
    Write-TextFile $statePath ('{' + [Environment]::NewLine + '  "hasCompletedOnboarding": true' + [Environment]::NewLine + '}' + [Environment]::NewLine)
    Write-Ok '已跳过首次登录引导'
  } else {
    $text = Read-Text $statePath
    try { $state = ConvertFrom-Json -InputObject $text } catch { $state = $null }
    if (!(Test-JsonObject $state)) { Write-Warn '.claude.json 无法识别，未修改。首次打开若出现登录页，请联系客服。' }
    elseif ($state.PSObject.Properties['hasCompletedOnboarding'] -and $state.hasCompletedOnboarding -eq $true) { Write-Ok '首次登录引导此前已完成' }
    else {
      if ($state.PSObject.Properties['hasCompletedOnboarding']) {
        $updated = [regex]::Replace($text, '"hasCompletedOnboarding"\s*:\s*false', '"hasCompletedOnboarding": true')
      } else {
        $brace = $text.IndexOf('{')
        $rest = $text.Substring($brace + 1)
        $separator = ','; if ($rest.Trim().StartsWith('}')) { $separator = '' }
        $updated = $text.Substring(0, $brace + 1) + '"hasCompletedOnboarding": true' + $separator + $rest
      }
      try { $check = ConvertFrom-Json -InputObject $updated } catch { $check = $null }
      if ((Test-JsonObject $check) -and $check.hasCompletedOnboarding -eq $true) {
        Backup-File $statePath
        Write-TextFile $statePath $updated
        Write-Ok '已跳过首次登录引导'
      } else { Write-Warn '.claude.json 结构特殊，未修改。首次打开若出现登录页，请联系客服。' }
    }
  }
  foreach ($name in @('ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_MODEL')) {
    if ([Environment]::GetEnvironmentVariable($name, 'User') -or [Environment]::GetEnvironmentVariable($name, 'Machine')) {
      Write-Warn ('系统环境变量里还有 ' + $name + '，可能与本配置冲突。不确定时请联系客服，不要随意删除。')
    }
  }
}

function Set-Codex([string]$Key, [string]$Model) {
  Write-Step '配置 Codex（桌面版和命令行版共用）'
  $root = [IO.Path]::Combine($script:UserHome, '.codex')
  if ($env:CODEX_HOME) { $root = $env:CODEX_HOME; Write-Warn ('检测到 CODEX_HOME，配置写入 ' + $root) }
  $configPath = [IO.Path]::Combine($root, 'config.toml')
  $lines = @()
  if (Test-Path -LiteralPath $configPath -PathType Leaf) { $lines = [regex]::Split((Read-Text $configPath), '\r?\n') }
  # Keep the user's other settings. Replace only the root model keys and our own provider table.
  $kept = New-Object System.Collections.Generic.List[string]
  $inRoot = $true; $skipping = $false
  foreach ($line in $lines) {
    $trimmed = $line.Trim()
    if ($trimmed.StartsWith('[')) {
      $inRoot = $false
      $skipping = $trimmed -match '^\[\s*model_providers\s*\.\s*"?huima"?\s*\]'
      if ($skipping) { continue }
    }
    if ($skipping) { continue }
    if ($inRoot -and $trimmed -match '^(model|model_provider|preferred_auth_method)\s*=') { continue }
    $kept.Add($line)
  }
  while ($kept.Count -gt 0 -and !$kept[$kept.Count - 1].Trim()) { $kept.RemoveAt($kept.Count - 1) }
  $out = New-Object System.Collections.Generic.List[string]
  $out.Add('model_provider = "huima"')
  $out.Add('model = "' + $Model + '"')
  $out.Add('preferred_auth_method = "apikey"')
  if ($kept.Count -gt 0) { $out.Add(''); $out.AddRange($kept) }
  $out.Add('')
  $out.Add('[model_providers.huima]')
  $out.Add('name = "汇码"')
  $out.Add('base_url = "' + $script:Settings.codex + '"')
  $out.Add('wire_api = "responses"')
  $out.Add('requires_openai_auth = true')
  $out.Add('')
  Backup-File $configPath
  Write-TextFile $configPath ($out -join "\n")
  Write-Ok ('已写入 ' + $configPath + '，模型 ' + $Model)
  $authPath = [IO.Path]::Combine($root, 'auth.json')
  Backup-File $authPath
  Write-TextFile $authPath (ConvertTo-Json -InputObject ([ordered]@{ OPENAI_API_KEY = $Key }))
  Write-Ok ('已写入 ' + $authPath + '（原有登录已备份）')
  foreach ($name in @('OPENAI_API_KEY', 'OPENAI_BASE_URL')) {
    if ([Environment]::GetEnvironmentVariable($name, 'User') -or [Environment]::GetEnvironmentVariable($name, 'Machine')) {
      Write-Warn ('系统环境变量里还有 ' + $name + '，可能与本配置冲突。不确定时请联系客服，不要随意删除。')
    }
  }
}

function Set-WorkBuddy([string]$Key, [string]$Model) {
  Write-Step '配置 WorkBuddy'
  $path = [IO.Path]::Combine($script:UserHome, '.workbuddy', 'models.json')
  $document = Read-JsonFile $path
  $entry = [pscustomobject][ordered]@{
    id = $Model; name = $Model; vendor = 'Custom'
    url = $script:Settings.workbuddy_url; apiKey = $Key
    maxInputTokens = [int]$script:Settings.workbuddy.max_input_tokens; maxOutputTokens = [int]$script:Settings.workbuddy.max_output_tokens
    supportsToolCall = [bool]$script:Settings.workbuddy.supports_tool_call
    supportsImages = [bool]$script:Settings.workbuddy.supports_images
    supportsReasoning = [bool]$script:Settings.workbuddy.supports_reasoning
  }
  $isOurs = { param($item) (Test-JsonObject $item) -and $item.PSObject.Properties['url'] -and ([string]$item.url).StartsWith($script:Settings.site) }
  # WorkBuddy itself creates models.json as a top-level array ([]) on first launch, so use that shape.
  if ($null -eq $document) {
    $document = @($entry)
  } elseif ($document -is [array]) {
    $document = @(@($document | Where-Object { !(& $isOurs $_) }) + $entry)
  } elseif ((Test-JsonObject $document) -and (!$document.PSObject.Properties['models'] -or $document.models -is [array])) {
    $models = @()
    if ($document.PSObject.Properties['models']) { $models = @($document.models | Where-Object { !(& $isOurs $_) }) }
    Set-Field $document 'models' @($models + $entry)
    $available = @()
    if ($document.PSObject.Properties['availableModels'] -and $document.availableModels -is [array]) { $available = @($document.availableModels) }
    if ($available -notcontains $Model) { $available = @($available + $Model) }
    Set-Field $document 'availableModels' $available
  } else { throw 'models.json 的格式无法识别，本项未修改。请改用 WorkBuddy 设置界面手动添加。' }
  Backup-File $path
  Write-TextFile $path (ConvertTo-Json -InputObject $document -Depth 16)
  Write-Ok ('已写入 ' + $path + '，模型 ' + $Model)
}

function Main {
  $data = ConvertFrom-Json -InputObject ($script:Utf8.GetString([Convert]::FromBase64String('__HUIMA_DATA__')))
  $payload = $data.tools
  $script:Settings = $data.settings
  # Defence in depth: the page already validated these, refuse anything that is not a plain https URL.
  foreach ($url in @($script:Settings.site, $script:Settings.codex, $script:Settings.workbuddy_url)) {
    if ([string]$url -notmatch '^https://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?$') { throw ('接口地址格式不正确：' + $url) }
  }
  $names = @($payload.PSObject.Properties.Name)
  $labels = @{ claude = 'Claude Code'; codex = 'Codex'; workbuddy = 'WorkBuddy' }
  Write-Host '========================================================'
  Write-Host '               汇码 · 一键配置'
  Write-Host '========================================================'
  Write-Host ('将配置：' + (($names | ForEach-Object { $labels[$_] }) -join '、'))
  Write-Host ('接口地址：' + $script:Settings.site)
  Write-Host '改动前会自动备份原文件，之后可用手册里的“恢复脚本”一键还原。'
  Write-Host ''
  Write-Host '请先关闭 Claude Code、Codex 和 WorkBuddy 窗口，再继续。' -ForegroundColor Yellow
  if ((Read-Host '准备好后输入 Y 并回车（其他内容取消）') -notmatch '^[Yy]$') { Write-Host '已取消，没有修改任何文件。'; return 0 }
  $failed = New-Object System.Collections.Generic.List[string]
  foreach ($name in $names) {
    $item = $payload.$name
    try {
      switch ($name) {
        'claude' {
          $roles = $null
          if ($item.PSObject.Properties['roles']) { $roles = $item.roles }
          Set-ClaudeCode $item.apiKey $item.model $roles
        }
        'codex' { Set-Codex $item.apiKey $item.model }
        'workbuddy' { Set-WorkBuddy $item.apiKey $item.model }
      }
    } catch {
      $failed.Add($labels[$name])
      Write-Host ('  [失败] ' + $_.Exception.Message) -ForegroundColor Red
    }
  }
  Write-Host ''
  if ($script:Backup) { Write-Host ('备份位置：' + $script:Backup) }
  if ($failed.Count -gt 0) {
    Write-Host ('未完成：' + ($failed -join '、') + '。其他软件已配置好，可以先使用。') -ForegroundColor Yellow
    return 1
  }
  Write-Host '配置完成！打开软件，按手册“第 5 步”发一条消息测试。' -ForegroundColor Green
  Write-Host ''
  Write-Host '这个文件里有你的 API Key，不要发给别人。'
  if ((Read-Host '输入 Y 并回车，关闭窗口时自动删除本文件（推荐）') -match '^[Yy]$') { return 10 }
  Write-Host '已保留本文件，请自行删除。'
  return 0
}
try { exit (Main) }
catch { Write-Host ('停止：' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
`;

const ROLLBACK = String.raw`
function Main {
  Write-Host '========================================================'
  Write-Host '               汇码 · 恢复配置'
  Write-Host '========================================================'
  if (!(Test-Path -LiteralPath $script:BackupRoot)) { Write-Host '没有找到汇码配置脚本留下的备份，无需恢复。'; return 0 }
  $latest = $null
  foreach ($dir in @(Get-ChildItem -LiteralPath $script:BackupRoot -Directory | Sort-Object Name -Descending)) {
    $manifestPath = [IO.Path]::Combine($dir.FullName, 'manifest.json')
    $manifest = Read-JsonFile $manifestPath
    if ($manifest -and $manifest.status -eq 'active') { $latest = [pscustomobject]@{ Dir = $dir.FullName; Manifest = $manifest; Path = $manifestPath }; break }
  }
  if (!$latest) { Write-Host '所有备份都已恢复过，没有需要恢复的内容。'; return 0 }
  Write-Host ('将恢复到这次配置之前的状态：' + $latest.Dir)
  foreach ($file in @($latest.Manifest.files)) {
    if ($file.existed) { Write-Host ('  还原 ' + $file.path) } else { Write-Host ('  删除（配置前不存在）' + $file.path) }
  }
  Write-Host ''
  Write-Host '请先关闭 Claude Code、Codex 和 WorkBuddy 窗口。' -ForegroundColor Yellow
  if ((Read-Host '输入 Y 并回车开始恢复（其他内容取消）') -notmatch '^[Yy]$') { Write-Host '已取消，没有修改任何文件。'; return 0 }
  foreach ($file in @($latest.Manifest.files)) {
    if ($file.existed) {
      [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($file.path)) | Out-Null
      Copy-Item -LiteralPath ([IO.Path]::Combine($latest.Dir, $file.copy)) -Destination $file.path -Force
    } elseif (Test-Path -LiteralPath $file.path -PathType Leaf) {
      Remove-Item -LiteralPath $file.path -Force
    }
  }
  $latest.Manifest.status = 'restored'
  [IO.File]::WriteAllText($latest.Path, (ConvertTo-Json -InputObject $latest.Manifest -Depth 5), $script:Utf8)
  Write-Host '恢复完成。重新打开软件即可回到之前的状态。' -ForegroundColor Green
  Write-Host '再运行一次本脚本，可以继续恢复更早的一次配置。'
  return 0
}
try { exit (Main) }
catch { Write-Host ('停止：' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
`;

// Exit code 10 means "done, delete this file": cmd deletes itself after PowerShell returns.
function wrapCmd(title, powershell) {
  const launcher = `@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul 2>nul
title ${title}
set "HUIMA_SELF=%~f0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$f=[IO.File]::ReadAllText($env:HUIMA_SELF,[Text.Encoding]::UTF8); $m='#==HUIMA_POWERSHELL=='; & ([scriptblock]::Create($f.Substring($f.LastIndexOf($m)+$m.Length)))"
set "HUIMA_EXIT=%errorlevel%"
echo.
pause
if not "%HUIMA_EXIT%"=="10" exit /b %HUIMA_EXIT%
(goto) 2>nul & del "%~f0"
#==HUIMA_POWERSHELL==
`;
  // String.raw keeps "\n" literally; PowerShell needs its own escape.
  return (launcher + powershell.replace(/"\\n"/g, '"`n"')).replace(/\r?\n/g, '\r\n');
}

// Settings the generated script needs from the manual configuration (all re-validated before use).
export function scriptSettings(cfg) {
  if (!isSafeConfig(cfg)) throw new Error('手册配置异常，请刷新页面后重试。');
  const {site, endpoints} = derive(cfg);
  const wb = cfg.workbuddy;
  return {
    site, codex: endpoints.codex, workbuddy_url: endpoints.workbuddy,
    workbuddy: {
      max_input_tokens: wb.max_input_tokens, max_output_tokens: wb.max_output_tokens,
      supports_tool_call: wb.supports_tool_call, supports_images: wb.supports_images, supports_reasoning: wb.supports_reasoning,
    },
  };
}

export function buildConfigCmd(input, cfg) {
  const tools = validateConfigInput(input);
  const data = {tools, settings: scriptSettings(cfg)};
  return wrapCmd('汇码一键配置', CORE + CONFIGURE.replace('__HUIMA_DATA__', base64Utf8(JSON.stringify(data))));
}

export function buildRollbackCmd() {
  return wrapCmd('汇码恢复配置', CORE + ROLLBACK);
}
