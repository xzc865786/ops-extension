/* Original, dependency-free Windows configurator. Secrets are data, never code. */
// Brand: 汇码. qiyuan_docs / QIYUAN_* identifiers deliberately stay unchanged
// so existing configurations, DPAPI backups and rollback history remain compatible.
const BASE_URL = 'https://api.tysy.top/v1';

export function validateSetupInput({ apiKey, model } = {}) {
  if (typeof apiKey !== 'string' || !apiKey || apiKey.length > 8192 || /[\s\x00-\x1f\x7f-\x9f]/.test(apiKey)) {
    throw new Error('请填写完整 API Key，不能包含空白或控制字符。');
  }
  if (typeof model !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(model)) {
    throw new Error('请填写准确模型 ID，只支持字母、数字及 . _ : / -。');
  }
  return { apiKey: apiKey.trim(), model };
}

function base64Utf8(value) {
  let binary = '';
  for (const byte of new TextEncoder().encode(value)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

// Kept readable inside every generated CMD. No remote code or execution-policy change.
export function getPowerShellCore() {
  const code = String.raw`
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$script:QyzUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
$script:QyzBegin = '# BEGIN QIYUAN DOCS PROVIDER (managed)'
$script:QyzEnd = '# END QIYUAN DOCS PROVIDER'

function Get-QyzHash([byte[]]$Bytes) {
  $sha = [Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
  finally { $sha.Dispose() }
}
function Get-QyzTextHash($Value) {
  if ($null -eq $Value) { return 'absent' }
  return Get-QyzHash $script:QyzUtf8.GetBytes($Value)
}
function Assert-QyzSafePath([string]$Path) {
  $check = [IO.Path]::GetFullPath($Path)
  while ($check) {
    if (Test-Path -LiteralPath $check) {
      $item = Get-Item -LiteralPath $check -Force
      if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing symbolic link/junction: $check" }
    }
    $parent = [IO.Path]::GetDirectoryName($check)
    if ($parent -eq $check) { break }
    $check = $parent
  }
}
function New-QyzContext([string]$Root, [switch]$Simulate) {
  $full = [IO.Path]::GetFullPath($Root)
  Assert-QyzSafePath $full
  return [pscustomobject]@{ Root=$full; Config=[IO.Path]::Combine($full,'config.toml'); Backups=[IO.Path]::Combine($full,'qiyuan-docs-backups'); Simulate=[bool]$Simulate; EnvFile=[IO.Path]::Combine($full,'test-user-env.json') }
}
function Get-QyzEnvironment($Context) {
  if ($Context.Simulate) {
    if (!(Test-Path -LiteralPath $Context.EnvFile)) { return $null }
    return ([IO.File]::ReadAllText($Context.EnvFile) | ConvertFrom-Json).value
  }
  return [Environment]::GetEnvironmentVariable('QIYUAN_API_KEY', 'User')
}
function Set-QyzEnvironment($Context, $Value) {
  if ($Context.Simulate) {
    [IO.File]::WriteAllText($Context.EnvFile, (@{value=$Value}|ConvertTo-Json -Compress), $script:QyzUtf8)
    return
  }
  [Environment]::SetEnvironmentVariable('QIYUAN_API_KEY', $Value, 'User')
}
function Protect-QyzValue([string]$Value) {
  Add-Type -AssemblyName System.Security
  return [Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect($script:QyzUtf8.GetBytes($Value), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))
}
function Unprotect-QyzValue([string]$Value) {
  Add-Type -AssemblyName System.Security
  return $script:QyzUtf8.GetString([Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String($Value), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))
}
function Get-QyzConfigState($Context) {
  Assert-QyzSafePath $Context.Config
  if (!(Test-Path -LiteralPath $Context.Config)) { return [pscustomobject]@{Exists=$false; Bytes=[byte[]]@(); Hash='absent'} }
  if ((Get-Item -LiteralPath $Context.Config).PSIsContainer) { throw 'config.toml is a directory.' }
  $bytes = [IO.File]::ReadAllBytes($Context.Config)
  if ($bytes.Length -gt 1048576) { throw 'Configuration exceeds the safe size limit. Please use CC Switch.' }
  return [pscustomobject]@{Exists=$true; Bytes=$bytes; Hash=(Get-QyzHash $bytes)}
}

# A deliberately conservative TOML subset. No multiline values, dotted assignments,
# array-of-tables, dates, implicit-table reuse, or uncertain syntax is rewritten.
function Get-QyzTokens([string]$Line) {
  $result = New-Object System.Collections.Generic.List[object]
  $i=0
  while ($i -lt $Line.Length) {
    $ch=$Line[$i]
    if ($ch -eq ' ' -or [int]$ch -eq 9) { $i++; continue }
    if ([char]::IsWhiteSpace($ch)) { throw 'Unsupported whitespace outside TOML strings.' }
    if ($ch -eq '#') { break }
    if ($ch -eq '"' -or $ch -eq "'") {
      $quote=$ch; $start=$i; $i++; $closed=$false
      while ($i -lt $Line.Length) {
        $c=$Line[$i]
        if ([int]$c -lt 32 -or [int]$c -eq 127) { throw 'Control character in TOML string.' }
        if ($c -eq $quote) { $i++; $closed=$true; break }
        if ($quote -eq '"' -and $c -eq '\') {
          $i++
          if ($i -ge $Line.Length) { throw 'Unclosed TOML escape.' }
          $e=$Line[$i]
          if ('btnfr"\'.IndexOf($e) -lt 0) {
            if ($e -ne 'u' -and $e -ne 'U') { throw 'Unsupported TOML escape.' }
            $count=4; if ($e -eq 'U') { $count=8 }
            if ($i+$count -ge $Line.Length -or $Line.Substring($i+1,$count) -notmatch '^[0-9A-Fa-f]+$') { throw 'Invalid TOML Unicode escape.' }
            $scalar=[Convert]::ToInt64($Line.Substring($i+1,$count),16)
            if ($scalar -gt 1114111 -or ($scalar -ge 55296 -and $scalar -le 57343)) { throw 'Invalid TOML Unicode scalar.' }
            $i+=$count
          }
        }
        $i++
      }
      if (!$closed) { throw 'Multiline or unclosed TOML string. Please use CC Switch.' }
      $result.Add([pscustomobject]@{Kind='string'; Raw=$Line.Substring($start,$i-$start)})
      continue
    }
    if ('[]=,.{}'.IndexOf($ch) -ge 0) { $result.Add([pscustomobject]@{Kind='punct';Raw=[string]$ch}); $i++; continue }
    $start=$i
    while ($i -lt $Line.Length -and ![char]::IsWhiteSpace($Line[$i]) -and '[]=,.{}#"'''.IndexOf($Line[$i]) -lt 0) { $i++ }
    if ($start -eq $i) { throw 'Unsupported TOML character.' }
    $result.Add([pscustomobject]@{Kind='bare';Raw=$Line.Substring($start,$i-$start)})
  }
  return ,$result.ToArray()
}
function Read-QyzValue($Tokens, [ref]$Position, [int]$Depth=0) {
  if ($Depth -gt 12 -or $Position.Value -ge $Tokens.Count) { throw 'Invalid or excessively nested TOML value.' }
  $token=$Tokens[$Position.Value]; $Position.Value++
  if ($token.Kind -eq 'string') { return }
  if ($token.Raw -eq '[') {
    if ($Position.Value -lt $Tokens.Count -and $Tokens[$Position.Value].Raw -eq ']') { $Position.Value++; return }
    while ($true) {
      Read-QyzValue $Tokens $Position ($Depth+1)
      if ($Position.Value -ge $Tokens.Count) { throw 'Multiline or unclosed TOML array. Please use CC Switch.' }
      if ($Tokens[$Position.Value].Raw -eq ']') { $Position.Value++; return }
      if ($Tokens[$Position.Value].Raw -ne ',') { throw 'Invalid TOML array separator.' }
      $Position.Value++
      if ($Position.Value -lt $Tokens.Count -and $Tokens[$Position.Value].Raw -eq ']') { $Position.Value++; return }
    }
  }
  if ($token.Kind -eq 'bare' -and $token.Raw -cmatch '^(true|false)$') { return }
  if ($token.Kind -eq 'bare' -and $token.Raw -cmatch '^[+-]?(0|[1-9][0-9]*)$') {
    $integer=[long]0
    if (![long]::TryParse($token.Raw,[Globalization.NumberStyles]::AllowLeadingSign,[Globalization.CultureInfo]::InvariantCulture,[ref]$integer)) { throw 'TOML integer exceeds the signed 64-bit range.' }
    return
  }
  throw 'Unsupported or complex TOML value. No changes made; use CC Switch.'
}
function Test-QyzToml([string[]]$Lines,[switch]$AllowManaged) {
  $section=''
  $tables=[Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::Ordinal)
  $keys=[Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::Ordinal)
  $rootModel=-1; $rootProvider=-1; $firstTable=$Lines.Count
  for ($lineNumber=0; $lineNumber -lt $Lines.Count; $lineNumber++) {
    $tokens=Get-QyzTokens $Lines[$lineNumber]
    if ($tokens.Count -eq 0) { continue }
    if ($tokens[0].Raw -eq '[') {
      if ($firstTable -eq $Lines.Count) { $firstTable=$lineNumber }
      if ($tokens.Count -lt 3 -or $tokens[-1].Raw -ne ']') { throw 'Unsupported TOML table syntax.' }
      $parts=New-Object System.Collections.Generic.List[string]
      for ($t=1; $t -lt $tokens.Count-1; $t++) {
        $part=$tokens[$t]
        if (($t % 2) -eq 0) { if ($part.Raw -ne '.') { throw 'Invalid TOML table path.' }; continue }
        if ($part.Kind -eq 'bare' -and $part.Raw -match '^[A-Za-z0-9_-]+$') { $parts.Add($part.Raw) }
        elseif ($part.Kind -eq 'string' -and ($part.Raw.StartsWith("'") -or $part.Raw -notmatch '\\')) {
          $name=$part.Raw.Substring(1,$part.Raw.Length-2)
          if (!$name -or $name.Contains('.')) { throw 'Empty or dotted quoted TOML table segments require manual configuration.' }
          $parts.Add($name)
        }
        else { throw 'Complex TOML table names are not automatically edited.' }
      }
      if (($tokens.Count % 2) -eq 0) { throw 'Invalid TOML table path.' }
      $section=$parts -join '.'
      if ($tables.ContainsKey($section) -or $keys.ContainsKey($section)) { throw 'Duplicate or conflicting TOML table.' }
      $prefix=''
      foreach ($piece in $parts) {
        if ($prefix) { $prefix+='.' }; $prefix+=$piece
        if ($keys.ContainsKey($prefix)) { throw 'TOML scalar conflicts with a table path.' }
      }
      $tables[$section]=$true
      continue
    }
    if ($tokens.Count -lt 3 -or $tokens[0].Kind -ne 'bare' -or $tokens[0].Raw -notmatch '^[A-Za-z0-9_-]+$' -or $tokens[1].Raw -ne '=') { throw 'Complex TOML assignment. Please use CC Switch.' }
    $key=$tokens[0].Raw; $qualified=$key; if ($section) { $qualified=$section+'.'+$key }
    if ($keys.ContainsKey($qualified) -or $tables.ContainsKey($qualified)) { throw 'Duplicate or conflicting TOML key.' }
    $keys[$qualified]=$true
    $pos=2; Read-QyzValue $tokens ([ref]$pos)
    if ($pos -ne $tokens.Count) { throw 'Unexpected TOML value content.' }
    if (!$section -and $key -ceq 'model') { $rootModel=$lineNumber }
    if (!$section -and $key -ceq 'model_provider') { $rootProvider=$lineNumber }
  }
  if (!$AllowManaged) {
    if ($tables.ContainsKey('model_providers.qiyuan_docs')) { throw 'An unmanaged qiyuan_docs provider already exists. Please use CC Switch.' }
    foreach ($table in $tables.Keys) {
      if ($table.StartsWith('model_providers.qiyuan_docs.',[StringComparison]::Ordinal)) { throw 'Unmanaged provider namespace conflict.' }
    }
    foreach ($key in $keys.Keys) {
      if ($key -ceq 'model_providers' -or $key -ceq 'model_providers.qiyuan_docs' -or $key.StartsWith('model_providers.qiyuan_docs.',[StringComparison]::Ordinal)) { throw 'Provider namespace conflict. Please use CC Switch.' }
    }
  }
  return [pscustomobject]@{Model=$rootModel; Provider=$rootProvider; FirstTable=$firstTable}
}
function Merge-QyzConfig([byte[]]$Bytes, [string]$Model) {
  if ($Model -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$') { throw 'Invalid model ID.' }
  $text=$script:QyzUtf8.GetString($Bytes)
  if ($text.StartsWith([string][char]0xFEFF,[StringComparison]::Ordinal)) { $text=$text.Substring(1) }
  if ($text.Contains([string][char]0)) { throw 'NUL byte in configuration.' }
  $newline="\n"; if ($text.Contains("\r\n")) { $newline="\r\n" }
  $lines=[regex]::Split($text,'\r?\n')
  $starts=@(); $ends=@()
  for ($i=0;$i -lt $lines.Count;$i++) {
    if ($lines[$i] -eq $script:QyzBegin) { $starts+=,$i }
    if ($lines[$i] -eq $script:QyzEnd) { $ends+=,$i }
  }
  if ($starts.Count -gt 0 -or $ends.Count -gt 0) {
    if ($starts.Count -ne 1 -or $ends.Count -ne 1 -or $ends[0] -lt $starts[0]) { throw 'Damaged managed provider markers.' }
    for ($i=$ends[0]+1;$i -lt $lines.Count;$i++) { if ($lines[$i].Trim()) { throw 'Managed provider must remain the final section.' } }
    $managed=$lines[($starts[0]+1)..($ends[0]-1)] -join "\n"
    $expected='(?s)^\[model_providers\.qiyuan_docs\]\nname = "(?:启元智作|汇码)"\nbase_url = "https://api\.tysy\.top/v1"\nwire_api = "responses"\nenv_key = "QIYUAN_API_KEY"\nrequires_openai_auth = false$'
    if ($managed -cnotmatch $expected) { throw 'Managed provider was edited. Refusing to overwrite it.' }
    if ($starts[0] -eq 0) { $lines=@() } else { $lines=$lines[0..($starts[0]-1)] }
  }
  $info=Test-QyzToml $lines
  $out=New-Object System.Collections.Generic.List[string]
  for ($i=0;$i -le $lines.Count;$i++) {
    if ($i -eq $info.FirstTable) {
      if ($info.Model -lt 0) { $out.Add('model = "'+$Model+'"') }
      if ($info.Provider -lt 0) { $out.Add('model_provider = "qiyuan_docs"') }
    }
    if ($i -eq $lines.Count) { break }
    if ($i -eq $info.Model) { $out.Add('model = "'+$Model+'"') }
    elseif ($i -eq $info.Provider) { $out.Add('model_provider = "qiyuan_docs"') }
    else { $out.Add($lines[$i]) }
  }
  $out.Add(''); $out.Add($script:QyzBegin)
  $out.Add('[model_providers.qiyuan_docs]'); $out.Add('name = "汇码"')
  $out.Add('base_url = "https://api.tysy.top/v1"'); $out.Add('wire_api = "responses"')
  $out.Add('env_key = "QIYUAN_API_KEY"'); $out.Add('requires_openai_auth = false')
  $out.Add($script:QyzEnd); $out.Add('')
  Test-QyzToml $out.ToArray() -AllowManaged | Out-Null
  return ,$script:QyzUtf8.GetBytes(($out -join $newline))
}
function Write-QyzManifest([string]$Directory, $Manifest) {
  $path=[IO.Path]::Combine($Directory,'manifest.json')
  [IO.File]::WriteAllText($path, ($Manifest | ConvertTo-Json -Depth 6), $script:QyzUtf8)
}
function Get-QyzHistory($Context) {
  Assert-QyzSafePath $Context.Backups
  if (!(Test-Path -LiteralPath $Context.Backups)) { return ,@() }
  $entries=@()
  foreach ($dir in Get-ChildItem -LiteralPath $Context.Backups -Directory) {
    if ($dir.Name -notmatch '^\d{19}-[0-9a-f]{32}$') { throw 'Unrecognized backup directory; manual review required.' }
    Assert-QyzSafePath $dir.FullName
    $manifestPath=[IO.Path]::Combine($dir.FullName,'manifest.json')
    Assert-QyzSafePath $manifestPath
    if (!(Test-Path -LiteralPath $manifestPath)) { throw 'Incomplete backup detected; manual review required.' }
    $manifest=[IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
    if ($manifest.version -ne 1 -or $manifest.status -notin @('active','rolled_back','failed_safe')) { throw 'Incomplete transaction detected; manual review required.' }
    if ($manifest.status -eq 'active') { $entries+=,[pscustomobject]@{Directory=$dir.FullName; Name=$dir.Name; Manifest=$manifest} }
  }
  return ,@($entries | Sort-Object Name -Descending)
}
function Enter-QyzLock($Context) {
  Assert-QyzSafePath $Context.Root
  [IO.Directory]::CreateDirectory($Context.Root) | Out-Null
  $path=[IO.Path]::Combine($Context.Root,'.qiyuan-docs.lock')
  try { $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
  catch { throw 'Another operation or a leftover lock exists. Do not run scripts simultaneously.' }
  return [pscustomobject]@{Stream=$stream;Path=$path}
}
function Exit-QyzLock($Lock) { $Lock.Stream.Dispose(); [IO.File]::Delete($Lock.Path) }
function Write-QyzConfig($Context, [byte[]]$Bytes, [string]$ExpectedHash) {
  if ((Get-QyzConfigState $Context).Hash -ne $ExpectedHash) { throw 'Configuration changed during the operation; refusing overwrite.' }
  $temp=[IO.Path]::Combine($Context.Root,'.qiyuan-'+[guid]::NewGuid().ToString('N')+'.tmp')
  try {
    [IO.File]::WriteAllBytes($temp,$Bytes)
    if ((Get-QyzConfigState $Context).Hash -ne $ExpectedHash) { throw 'Configuration changed during the operation; refusing overwrite.' }
    if ($ExpectedHash -eq 'absent') { [IO.File]::Move($temp,$Context.Config) }
    else { [IO.File]::Replace($temp,$Context.Config,[System.Management.Automation.Language.NullString]::Value) }
  } finally { if (Test-Path -LiteralPath $temp) { [IO.File]::Delete($temp) } }
}
function Invoke-QyzSetup($Context,[string]$ApiKey,[string]$Model) {
  if ([string]::IsNullOrWhiteSpace($ApiKey) -or $ApiKey.Length -gt 8192 -or $ApiKey -match '[\s\x00-\x1f\x7f-\x9f]') { throw 'Invalid API key.' }
  $lock=Enter-QyzLock $Context
  try {
    $history=Get-QyzHistory $Context
    $before=Get-QyzConfigState $Context
    $oldEnv=Get-QyzEnvironment $Context
    if ($history.Count -gt 0) {
      if ($before.Hash -ne $history[0].Manifest.after_hash -or (Get-QyzTextHash $oldEnv) -ne $history[0].Manifest.after_env_hash) { throw 'Current configuration or key changed outside this tool. Refusing to overwrite; use CC Switch.' }
    }
    $after=Merge-QyzConfig $before.Bytes $Model
    $id=([DateTime]::UtcNow.Ticks.ToString('D19'))+'-'+[guid]::NewGuid().ToString('N')
    [IO.Directory]::CreateDirectory($Context.Backups) | Out-Null
    $directory=[IO.Path]::Combine($Context.Backups,$id)
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $oldProtected=$null; if ($null -ne $oldEnv) { $oldProtected=Protect-QyzValue $oldEnv }
    $manifest=[pscustomobject]@{version=1;status='pending';created_utc=[DateTime]::UtcNow.ToString('o');before_exists=$before.Exists;before_hash=$before.Hash;after_hash=(Get-QyzHash $after);before_env_exists=($null -ne $oldEnv);before_env_dpapi=$oldProtected;after_env_hash=(Get-QyzTextHash $ApiKey)}
    if ($before.Exists) { [IO.File]::WriteAllBytes([IO.Path]::Combine($directory,'config.before.bin'),$before.Bytes) }
    Write-QyzManifest $directory $manifest
    $wrote=$false; $envWrote=$false
    try {
      if ((Get-QyzTextHash (Get-QyzEnvironment $Context)) -ne (Get-QyzTextHash $oldEnv)) { throw 'User environment changed during backup.' }
      Write-QyzConfig $Context $after $before.Hash; $wrote=$true
      Set-QyzEnvironment $Context $ApiKey; $envWrote=$true
      $manifest.status='active'; Write-QyzManifest $directory $manifest
    } catch {
      $originalError=$_
      try {
        if ($envWrote) {
          if ((Get-QyzTextHash (Get-QyzEnvironment $Context)) -ne $manifest.after_env_hash) { throw 'Environment conflict during recovery.' }
          Set-QyzEnvironment $Context $oldEnv
        }
        if ($wrote) {
          if ((Get-QyzConfigState $Context).Hash -ne $manifest.after_hash) { throw 'Configuration conflict during recovery.' }
          if ($before.Exists) { Write-QyzConfig $Context $before.Bytes $manifest.after_hash }
          else { [IO.File]::Move($Context.Config,[IO.Path]::Combine($directory,'failed-created-config.toml')) }
        }
        $manifest.status='failed_safe'; Write-QyzManifest $directory $manifest
      } catch { throw "Operation incomplete. Keep backups and ask support: $directory" }
      throw $originalError
    }
    return [pscustomobject]@{Backup=$directory;Hash=$manifest.after_hash}
  } finally { Exit-QyzLock $lock }
}
function Invoke-QyzRollback($Context) {
  $lock=Enter-QyzLock $Context
  try {
    $history=Get-QyzHistory $Context
    if ($history.Count -eq 0) { throw 'No active backup remains; nothing was changed.' }
    $entry=$history[0]; $manifest=$entry.Manifest
    $current=Get-QyzConfigState $Context; $currentEnv=Get-QyzEnvironment $Context
    if ($current.Hash -ne $manifest.after_hash -or (Get-QyzTextHash $currentEnv) -ne $manifest.after_env_hash) { throw 'Later manual changes detected. Rollback refused to protect your configuration/key.' }
    $oldEnv=$null; if ($manifest.before_env_exists) { $oldEnv=Unprotect-QyzValue $manifest.before_env_dpapi }
    $beforeBytes=[byte[]]@()
    if ($manifest.before_exists) {
      $backupPath=[IO.Path]::Combine($entry.Directory,'config.before.bin'); Assert-QyzSafePath $backupPath
      $beforeBytes=[IO.File]::ReadAllBytes($backupPath)
      if ((Get-QyzHash $beforeBytes) -ne $manifest.before_hash) { throw 'Backup integrity check failed. Nothing changed.' }
    }
    $savedAfter=[IO.Path]::Combine($entry.Directory,'config.after-rollback.toml')
    if (Test-Path -LiteralPath $savedAfter) { throw 'Rollback target already exists; manual review required.' }
    $manifest.status='rolling_back'; Write-QyzManifest $entry.Directory $manifest
    $wrote=$false; $envWrote=$false
    try {
      if ($manifest.before_exists) {
        [IO.File]::WriteAllBytes($savedAfter,$current.Bytes)
        Write-QyzConfig $Context $beforeBytes $current.Hash
      } else {
        if ((Get-QyzConfigState $Context).Hash -ne $current.Hash) { throw 'Configuration changed during rollback.' }
        [IO.File]::Move($Context.Config,$savedAfter)
      }
      $wrote=$true
      if ((Get-QyzTextHash (Get-QyzEnvironment $Context)) -ne $manifest.after_env_hash) { throw 'Environment changed during rollback.' }
      Set-QyzEnvironment $Context $oldEnv; $envWrote=$true
      $manifest.status='rolled_back'; Write-QyzManifest $entry.Directory $manifest
    } catch {
      $originalError=$_
      try {
        if ($envWrote) {
          if ((Get-QyzTextHash (Get-QyzEnvironment $Context)) -ne (Get-QyzTextHash $oldEnv)) { throw 'Recovery environment conflict.' }
          Set-QyzEnvironment $Context $currentEnv
        }
        if ($wrote) { Write-QyzConfig $Context $current.Bytes $manifest.before_hash }
        if (Test-Path -LiteralPath $savedAfter) { [IO.File]::Move($savedAfter,([IO.Path]::Combine($entry.Directory,'failed-rollback-'+[guid]::NewGuid().ToString('N')+'.toml'))) }
        $manifest.status='active'; Write-QyzManifest $entry.Directory $manifest
      } catch { throw "Rollback incomplete. Keep backups and ask support: $($entry.Directory)" }
      throw $originalError
    }
    return [pscustomobject]@{Backup=$entry.Directory;RestoredHash=$manifest.before_hash}
  } finally { Exit-QyzLock $lock }
}
`;
  return code.replace(/"\\r\\n"/g, '"`r`n"').replace(/"\\n"/g, '"`n"').replace(/"\\r"/g, '"`r"');
}

function cmdFor(mode, data) {
  const encoded = base64Utf8(JSON.stringify(data));
  const main = String.raw`
try {
  if ($env:CODEX_HOME) { throw '检测到自定义 CODEX_HOME。本脚本只支持默认用户配置，请改用 CC Switch 或手动合并。' }
  $profilePath=[Environment]::GetFolderPath('UserProfile')
  if ([string]::IsNullOrWhiteSpace($profilePath)) { throw '无法定位当前用户目录。' }
  $ctx=New-QyzContext ([IO.Path]::Combine($profilePath,'.codex'))
  $mode='__QIYUAN_MODE__'
  $payload=$script:QyzUtf8.GetString([Convert]::FromBase64String('__QIYUAN_DATA__')) | ConvertFrom-Json
  Write-Host ''
  Write-Host '汇码 Codex 配置工具'
  if ($mode -eq 'setup') { Write-Host ('当前操作: 配置汇码，模型 '+$payload.model) }
  else { Write-Host '当前操作: 回滚最近一次配置，恢复当时的完整文件和用户环境变量。' }
  Write-Host ('目标文件: '+$ctx.Config)
  Write-Host ('备份目录: '+$ctx.Backups)
  Write-Host '仅修改 model / model_provider、本站 provider 段和用户级 QIYUAN_API_KEY。'
  Write-Host 'qiyuan_docs、QIYUAN_API_KEY 和旧备份目录是兼容标识，继续保留以便回滚历史配置。'
  Write-Host '不修改 auth.json、OPENAI_API_KEY、审批、沙箱或 MCP。不下载或运行其他代码。'
  Write-Host '请先完全退出 Codex 和 CC Switch；本脚本不会替你终止任何进程。'
  Write-Host '若回滚，按最近一次配置优先恢复；检测到后续人工修改会停止。'
  if ($mode -eq 'setup') { Write-Host '脚本包含你的密钥，请不要发送给他人。完成后妥善删除下载的配置脚本。' }
  else { Write-Host '请使用创建备份时的同一个 Windows 用户，备份中的旧密钥受该用户的 DPAPI 保护。' }
  if ((Read-Host '输入 Y 继续，其他内容取消') -cne 'Y') { Write-Host '已取消，未修改配置。'; exit 0 }
  if ($mode -eq 'setup') { $result=Invoke-QyzSetup $ctx $payload.apiKey $payload.model }
  else { $result=Invoke-QyzRollback $ctx }
  Write-Host '完成。请重新启动 Codex / CC Switch，旧进程不会自动获得新环境变量。'
  Write-Host '如果仍读取旧环境，请先注销并重新登录 Windows。不要再次反复执行。'
  Write-Host ('备份已保留: '+$result.Backup)
  Write-Host '配置完成不等于模型连通；请新建任务发送一句短消息验证。'
  exit 0
} catch {
  Write-Host ('停止: '+$_.Exception.Message) -ForegroundColor Red
  Write-Host '请保留备份。复杂配置请使用 CC Switch；不要为运行脚本关闭安全保护。'
  exit 1
}
`.replace('__QIYUAN_DATA__', encoded).replace('__QIYUAN_MODE__', mode);
  // Decode JS String.raw newline placeholders used for PowerShell strings, not user data.
  const ps = (getPowerShellCore() + main).replace(/"\\r\\n"/g, '"`r`n"').replace(/"\\n"/g, '"`n"').replace(/"\\r"/g, '"`r"');
  const launcher = `@echo off
setlocal DisableDelayedExpansion
set "QIYUAN_DOCS_SELF=%~f0"
powershell.exe -NoLogo -NoProfile -Command "$f=[IO.File]::ReadAllText($env:QIYUAN_DOCS_SELF); $m='#==QIYUAN_POWERSHELL=='; $s=$f.Substring($f.LastIndexOf($m)+$m.Length); & ([scriptblock]::Create($s))"
set "qiyuan_result=%errorlevel%"
echo.
pause
exit /b %qiyuan_result%
#==QIYUAN_POWERSHELL==
`;
  return (launcher + ps).replace(/\r?\n/g, '\r\n');
}

export function buildSetupCmd(input) { return cmdFor('setup', validateSetupInput(input)); }
export function buildRollbackCmd() { return cmdFor('rollback', {}); }
export const QIYUAN_BASE_URL = BASE_URL;
