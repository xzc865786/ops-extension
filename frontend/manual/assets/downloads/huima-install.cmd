@echo off
rem Keep CRLF line endings when packaging or downloading this Windows script.
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>nul
title 汇码 · 一键安装
rem The manual rewrites the next line with the tools picked on the page; empty shows a menu.
set "HUIMA_TOOLS="
set "CC_SETUP_FILE=%~f0"
set "CC_SETUP_MODE=%~1"
set "CC_SETUP_PAUSE=1"
if /i "%~1"=="--no-pause" set "CC_SETUP_PAUSE=0"
if /i "%~2"=="--no-pause" set "CC_SETUP_PAUSE=0"
set "CC_SETUP_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "CC_SETUP_PS=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
"%CC_SETUP_PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:CC_SETUP_FILE,[Text.Encoding]::UTF8); $m='# POWERSHELL_'+'PAYLOAD'; & ([scriptblock]::Create($s.Substring($s.IndexOf($m)+$m.Length)))"
set "CC_SETUP_EXIT=%ERRORLEVEL%"
echo.
if "%CC_SETUP_PAUSE%"=="1" pause
exit /b %CC_SETUP_EXIT%
# POWERSHELL_PAYLOAD
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Get-Setting([string]$Name, [string]$Default, [string]$Pattern) {
    # The manual page writes admin-configured values as `set "NAME=value"` lines at the top of this file.
    # Anything missing or not matching the expected format falls back to the built-in default.
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ($value -and $value -cmatch $Pattern) { return $value }
    return $Default
}
$script:UrlPattern = '^https://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?$'
$script:PackagePattern = '^(@[a-z0-9][a-z0-9._-]{0,100}/)?[a-z0-9][a-z0-9._-]{0,100}$'
$script:Registry = Get-Setting 'HUIMA_NPM_REGISTRY' 'https://registry.npmmirror.com' $script:UrlPattern
$script:OfficialRegistry = Get-Setting 'HUIMA_NPM_REGISTRY_FALLBACK' 'https://registry.npmjs.org' $script:UrlPattern
$script:NodeMirror = Get-Setting 'HUIMA_NODE_MIRROR' 'https://registry.npmmirror.com/-/binary/node' $script:UrlPattern
$script:NodeMinimum = [int](Get-Setting 'HUIMA_NODE_MIN' '22' '^\d{2}$')
$script:NodeLts = [int](Get-Setting 'HUIMA_NODE_LTS' '24' '^\d{2}$')
if ($script:NodeMinimum -gt $script:NodeLts) { $script:NodeMinimum = $script:NodeLts }
$script:ClaudePackage = Get-Setting 'HUIMA_CLAUDE_PACKAGE' '@anthropic-ai/claude-code' $script:PackagePattern
$script:CodexPackage = Get-Setting 'HUIMA_CODEX_PACKAGE' '@openai/codex' $script:PackagePattern
$script:CodexStoreId = Get-Setting 'HUIMA_CODEX_STORE_ID' '9PLM9XGG6VKS' '^[A-Z0-9]{12}$'
$script:WorkBuddyWingetId = Get-Setting 'HUIMA_WORKBUDDY_WINGET_ID' 'Tencent.WorkBuddy' '^[A-Za-z0-9][A-Za-z0-9-]{0,63}(\.[A-Za-z0-9][A-Za-z0-9-]{0,63}){1,3}$'
$script:WorkBuddySite = Get-Setting 'HUIMA_WORKBUDDY_SITE' 'https://www.workbuddy.cn/' $script:UrlPattern
$script:WorkBuddySizeMb = Get-Setting 'HUIMA_WORKBUDDY_SIZE_MB' '500' '^\d{1,5}$'
$script:Npm = $null
$script:Prefix = $null
$script:WorkDir = $null
$script:Winget = $null
$script:NpmReady = $false
$script:Results = [ordered]@{}

function Write-Step([string]$Message) {
    Write-Host "`n$Message" -ForegroundColor Cyan
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    # Include inherited entries used by portable installations and version managers.
    $env:Path = "$machine;$user;$env:Path"
}

function Add-UserPath([string]$Directory) {
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($user -split ';' | Where-Object { $_ })
    $found = $false
    foreach ($entry in $entries) {
        if ([Environment]::ExpandEnvironmentVariables($entry).TrimEnd('\') -ieq $Directory.TrimEnd('\')) {
            $found = $true
        }
    }
    if (-not $found) {
        [Environment]::SetEnvironmentVariable('Path', (($entries + $Directory) -join ';'), 'User')
    }
    $env:Path = "$Directory;$env:Path"
}

function Find-Program([string]$Name) {
    # Explicit extensions avoid npm.ps1 / codex.ps1 execution-policy errors.
    foreach ($extension in @('exe', 'cmd')) {
        $command = Get-Command "$Name.$extension" -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $command.Source }
    }
    return $null
}

function Get-ProgramVersion([string]$File) {
    if (-not $File -or -not (Test-Path -LiteralPath $File -PathType Leaf)) { return $null }
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& $File --version 2>&1)
        $code = $LASTEXITCODE
    } catch { return $null }
    finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { return $null }
    return ($lines | ForEach-Object { "$_" } | Where-Object { $_ -match '\d+\.\d+\.\d+' } | Select-Object -Last 1)
}

function Test-NodeVersion([string]$Version) {
    return ($Version -match '^v(\d+)\.' -and [int]$Matches[1] -ge $script:NodeMinimum)
}

function Test-NodeArchitecture([string]$File) {
    if (-not $File) { return $false }
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $architecture = @(& $File -p 'process.arch' 2>&1)
        return ($LASTEXITCODE -eq 0 -and ($architecture -join '').Trim() -in @('x64', 'arm64'))
    } catch { return $false }
    finally { $ErrorActionPreference = $previous }
}

function Invoke-Npm([string[]]$Arguments) {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $script:Npm @Arguments 2>&1 | ForEach-Object { Write-Host "$_" }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { throw "npm 执行失败（退出码 $code），请查看上面的具体错误。" }
}

function Get-Download([string]$Url, [string]$Destination, [int]$Timeout = 240) {
    Write-Host "  下载：$Url"
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec $Timeout -ErrorAction Stop
    } catch {
        Write-Host '  常规下载失败，尝试直连（不修改现有代理设置）。' -ForegroundColor Yellow
        # Windows PowerShell 5.1 has no Invoke-WebRequest -NoProxy option.
        $request = [Net.HttpWebRequest]::Create($Url)
        $request.Proxy = $null
        $request.Timeout = $Timeout * 1000
        $request.ReadWriteTimeout = $Timeout * 1000
        $response = $null
        $stream = $null
        $file = $null
        try {
            $response = $request.GetResponse()
            $stream = $response.GetResponseStream()
            $file = [IO.File]::Create($Destination)
            $stream.CopyTo($file)
        } finally {
            if ($file) { $file.Dispose() }
            if ($stream) { $stream.Dispose() }
            if ($response) { $response.Dispose() }
        }
    }
    if ((Get-Item -LiteralPath $Destination).Length -eq 0) { throw '下载文件为空。' }
}

function Get-NodeInstaller([string]$Architecture) {
    # Read index.json: mirror latest-v24.x aliases can lag behind actual releases.
    foreach ($base in @($script:NodeMirror, 'https://nodejs.org/dist')) {
        try {
            $index = Join-Path $script:WorkDir 'node-index.json'
            Get-Download "$base/index.json" $index 40
            $releases = Get-Content -LiteralPath $index -Raw -Encoding UTF8 | ConvertFrom-Json
            $release = $releases |
                Where-Object { $_.version -match "^v$($script:NodeLts)\." -and $_.lts -and $_.files -contains "win-$Architecture-msi" } |
                Sort-Object { [version]$_.version.TrimStart('v') } -Descending | Select-Object -First 1
            if (-not $release) { throw "没有找到适用的 Node.js $($script:NodeLts) LTS 安装包。" }
            $filename = "node-$($release.version)-$Architecture.msi"
            $checksumFile = Join-Path $script:WorkDir 'SHASUMS256.txt'
            Get-Download "$base/$($release.version)/SHASUMS256.txt" $checksumFile 40
            $pattern = '^([0-9a-fA-F]{64})\s+\*?' + [regex]::Escape($filename) + '$'
            $expected = $null
            foreach ($line in Get-Content -LiteralPath $checksumFile) {
                if ($line.Trim() -match $pattern) { $expected = $Matches[1]; break }
            }
            if (-not $expected) { throw '下载列表中缺少安装包校验信息。' }
            $installer = Join-Path $script:WorkDir $filename
            Get-Download "$base/$($release.version)/$filename" $installer
            if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ine $expected) {
                throw 'Node.js 下载文件校验失败，将尝试另一个下载源。'
            }
            Write-Host "  文件校验通过：$($release.version) / $Architecture" -ForegroundColor Green
            return $installer
        } catch { Write-Host "  当前下载源未成功：$($_.Exception.Message)" -ForegroundColor Yellow }
    }
    throw 'Node.js 下载失败。请检查网络或代理后重新双击脚本。'
}

function Ensure-Node([string]$Architecture) {
    Write-Step '准备 Node.js 和 npm'
    $node = Find-Program 'node'
    $version = Get-ProgramVersion $node
    $npm = if ($node) { Join-Path (Split-Path -Parent $node) 'npm.cmd' } else { $null }
    if ((Test-NodeVersion $version) -and (Test-NodeArchitecture $node) -and (Get-ProgramVersion $npm)) {
        $script:Npm = $npm
        Add-UserPath (Split-Path -Parent $node)
        Write-Host "  已安装 Node.js $version，满足要求，跳过下载。" -ForegroundColor Green
        return
    }
    Write-Host "  需要安装或修复 Node.js $($script:NodeLts) LTS（现有版本：$version）。"
    $installer = Get-NodeInstaller $Architecture
    Write-Host '  即将自动安装 Node.js；如果 Windows 弹出授权窗口，请点击“是”。'
    Write-Host '  安装期间请等待，不需要勾选额外开发工具。'
    $msiLog = Join-Path $script:WorkDir 'node-install.log'
    $arguments = '/i "{0}" /passive /norestart /L*v "{1}"' -f $installer, $msiLog
    try {
        $process = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    } catch { throw 'Node.js 安装未启动，可能取消了 Windows 授权。请重新运行，并在授权窗口选择“是”。' }
    if ($process.ExitCode -notin @(0, 3010, 1641)) {
        throw "Node.js 安装失败（退出码 $($process.ExitCode)）。安装日志：$msiLog"
    }
    if ($process.ExitCode -in @(3010, 1641)) { Write-Host '  Windows 提示需要重启；若后面验证失败，请重启后再运行。' -ForegroundColor Yellow }
    Refresh-Path
    $node = Find-Program 'node'
    $version = Get-ProgramVersion $node
    if (-not (Test-NodeVersion $version) -or -not (Test-NodeArchitecture $node)) {
        throw '当前 node 命令仍未指向 64 位 Node.js 22 以上版本。请关闭全部终端后重试；使用 nvm 等版本管理器时，请先切换到 64 位 Node.js 24。'
    }
    $script:Npm = Join-Path (Split-Path -Parent $node) 'npm.cmd'
    if (-not (Get-ProgramVersion $script:Npm)) { throw 'Node.js 已安装，但 npm 未能运行。请重新运行安装程序并修复 npm。' }
    Add-UserPath (Split-Path -Parent $node)
    Write-Host "  Node.js $version 已就绪。" -ForegroundColor Green
}

function Configure-Npm {
    Write-Step '配置国内下载源和命令路径'
    Invoke-Npm @('config', 'set', 'registry', $script:Registry, '--location=user')
    # Keep a working custom prefix; fall back to the normal user directory if protected.
    $prefixLines = @(& $script:Npm config get prefix)
    if ($LASTEXITCODE -ne 0) { throw '无法读取 npm 安装位置。' }
    $prefix = ($prefixLines -join '').Trim()
    if (-not $prefix -or -not [IO.Path]::IsPathRooted($prefix)) { throw 'npm 全局安装位置不是有效的绝对路径。' }
    $probe = $null
    try {
        New-Item -ItemType Directory -Path $prefix -Force | Out-Null
        $probe = Join-Path $prefix ('.huima-write-test-' + [guid]::NewGuid().ToString('N'))
        [IO.File]::WriteAllText($probe, '')
    } catch {
        $prefix = Join-Path $env:APPDATA 'npm'
        New-Item -ItemType Directory -Path $prefix -Force | Out-Null
        Invoke-Npm @('config', 'set', 'prefix', $prefix, '--location=user')
        Write-Host '  原 npm 安装位置不可写，已切换为当前用户的安装目录。'
    } finally {
        if ($probe -and (Test-Path -LiteralPath $probe)) { Remove-Item -LiteralPath $probe -Force }
    }
    $script:Prefix = $prefix
    Add-UserPath $prefix
    Write-Host "  安装位置：$prefix"
    Write-Host "  下载源：$($script:Registry)；失败时自动尝试 npm 官方源。"
}

function Write-ToolLauncher([string]$Command, [string]$Package) {
    # npm 10's generated CMD uses an unquoted SET dp0. Quote paths so Windows
    # usernames containing shell characters do not break the installed commands.
    $manifestFile = Join-Path $script:Prefix "node_modules\$Package\package.json"
    $manifest = Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $entry = if ($manifest.bin -is [string]) { $manifest.bin } else { $manifest.bin.$Command }
    if (-not $entry) { throw "$Package 未提供 $Command 启动入口。" }
    $relative = ("node_modules\$Package\$entry").Replace('/', '\')
    if ($entry -match '\.exe$') {
        $launch = '"%~dp0{0}" %*' -f $relative
    } else {
        $launch = 'node.exe "%~dp0{0}" %*' -f $relative
    }
    $content = "@echo off`r`nsetlocal DisableDelayedExpansion`r`n$launch`r`nexit /b %errorlevel%`r`n"
    [IO.File]::WriteAllText((Join-Path $script:Prefix "$Command.cmd"), $content, (New-Object Text.UTF8Encoding($false)))
    Remove-PowerShellShim $script:Prefix $Command
}

function Remove-PowerShellShim([string]$Directory, [string]$Command) {
    # npm also writes a .ps1 shim. PowerShell prefers it over the .cmd and the default execution
    # policy blocks it ("禁止运行脚本"). Without it, typing the command in PowerShell runs the .cmd.
    $shim = Join-Path $Directory "$Command.ps1"
    if ((Test-Path -LiteralPath $shim) -and (Test-Path -LiteralPath (Join-Path $Directory "$Command.cmd"))) {
        Remove-Item -LiteralPath $shim -Force
    }
}

function Install-Tool([string]$Command, [string]$Package, [string]$Title) {
    Write-Step "安装 $Title"
    $existing = Find-Program $Command
    $version = Get-ProgramVersion $existing
    if ($version) {
        Add-UserPath (Split-Path -Parent $existing)
        Remove-PowerShellShim (Split-Path -Parent $existing) $Command
        Write-Host "  已安装：$version，跳过重复安装。" -ForegroundColor Green
        return $true
    }
    $sources = @(
        @{ Registry = $script:Registry; Direct = $false },
        @{ Registry = $script:Registry; Direct = $true },
        @{ Registry = $script:OfficialRegistry; Direct = $false },
        @{ Registry = $script:OfficialRegistry; Direct = $true }
    )
    foreach ($source in $sources) {
        try {
            $registry = $source.Registry
            Write-Host "  正在安装，请耐心等待。下载源：$registry"
            $arguments = @('install', '--global', "$Package@latest", '--prefix', $script:Prefix,
                '--registry', $registry, '--include=optional', '--ignore-scripts=false',
                '--no-audit', '--no-fund', '--fetch-retries=1', '--fetch-timeout=120000',
                # npm 11 warns (and later npm blocks) package install scripts unless allowed; Claude Code's
                # postinstall copies its native binary into place. Older npm ignores the unknown option.
                "--allow-scripts=$Package")
            if ($source.Direct) {
                Write-Host '  本次尝试直连，不修改原有代理设置。'
                # npm 10 treats '*' literally here; explicit domains work on npm 10/11.
                $arguments += '--noproxy=' + ([Uri]$script:Registry).Host + ',' + ([Uri]$script:OfficialRegistry).Host
            }
            Invoke-Npm $arguments
            Write-ToolLauncher $Command $Package
            # Verify the newly installed file, not an unrelated old copy on PATH.
            $installed = Join-Path $script:Prefix "$Command.cmd"
            $version = Get-ProgramVersion $installed
            if (-not $version) { throw "$Title 安装命令已结束，但版本检查未通过。" }
            Write-Host "  安装成功：$version" -ForegroundColor Green
            return $true
        } catch { Write-Host "  此次安装未成功：$($_.Exception.Message)" -ForegroundColor Yellow }
    }
    Write-Host "  $Title 未安装成功，继续安装其他软件。" -ForegroundColor Red
    return $false
}

function Initialize-Npm([string]$Architecture) {
    if ($script:NpmReady) { return }
    Ensure-Node $Architecture
    Configure-Npm
    $script:NpmReady = $true
}

function Invoke-Winget([string[]]$Arguments) {
    # Let winget draw its own progress directly in this window.
    $process = Start-Process -FilePath $script:Winget -ArgumentList $Arguments -NoNewWindow -Wait -PassThru
    return $process.ExitCode
}

function Test-WingetSuccess([int]$Code) {
    # 0x8A15002B: no newer version available; 0x8A150061: already installed.
    return ($Code -in @(0, 0x8A15002B, 0x8A150061))
}

function Install-ClaudeCode([string]$Architecture) {
    try {
        Initialize-Npm $Architecture
        $script:Results['Claude Code'] = if (Install-Tool 'claude' $script:ClaudePackage 'Claude Code') { 'ok' } else { 'fail' }
    } catch {
        Write-Host "  Claude Code 未安装：$($_.Exception.Message)" -ForegroundColor Red
        $script:Results['Claude Code'] = 'fail'
    }
}

function Install-CodexDesktop([string]$Architecture) {
    Write-Step '安装 Codex 桌面版（微软商店）'
    if ($script:Winget) {
        Write-Host '  正在通过微软商店安装，首次可能需要几分钟。'
        $code = Invoke-Winget @('install', '--id', $script:CodexStoreId, '--source', 'msstore', '--exact',
            '--accept-package-agreements', '--accept-source-agreements')
        if (Test-WingetSuccess $code) {
            Write-Host '  Codex 桌面版已安装。在开始菜单搜索“Codex”即可打开。' -ForegroundColor Green
            $script:Results['Codex 桌面版'] = 'ok'
            return
        }
        Write-Host "  微软商店安装未成功（代码 $code）。" -ForegroundColor Yellow
    } else {
        Write-Host '  这台电脑没有 winget（应用安装程序），无法自动安装桌面版。' -ForegroundColor Yellow
    }
    $script:Results['Codex 桌面版'] = 'fail'
    try { Start-Process ('ms-windows-store://pdp/?ProductId=' + $script:CodexStoreId) } catch { }
    Write-Host '  已尝试打开微软商店的 Codex 页面，稍后可以在那里点“获取”手动安装。'
    Write-Host '  现在先改装 Codex 命令行版，配置方法相同，在终端里使用。'
    try {
        Initialize-Npm $Architecture
        $script:Results['Codex 命令行版'] = if (Install-Tool 'codex' $script:CodexPackage 'Codex 命令行版') { 'ok' } else { 'fail' }
    } catch {
        Write-Host "  Codex 命令行版未安装：$($_.Exception.Message)" -ForegroundColor Red
        $script:Results['Codex 命令行版'] = 'fail'
    }
}

function Install-WorkBuddy {
    Write-Step '安装 WorkBuddy（腾讯官方安装包）'
    if ($script:Winget) {
        Write-Host ('  正在下载 WorkBuddy 安装包（约 ' + $script:WorkBuddySizeMb + ' MB），请耐心等待。')
        $code = Invoke-Winget @('install', '--id', $script:WorkBuddyWingetId, '--source', 'winget', '--exact',
            '--accept-package-agreements', '--accept-source-agreements')
        if (Test-WingetSuccess $code) {
            Write-Host '  WorkBuddy 已安装。在开始菜单或桌面找到 WorkBuddy 打开，并按提示登录。' -ForegroundColor Green
            $script:Results['WorkBuddy'] = 'ok'
            return
        }
        Write-Host "  自动安装未成功（代码 $code）。" -ForegroundColor Yellow
    }
    try { Start-Process $script:WorkBuddySite } catch { }
    Write-Host '  已打开 WorkBuddy 官网：点击“下载”，再双击下载好的安装包完成安装。'
    $script:Results['WorkBuddy'] = 'manual'
}

function Get-Selection {
    $raw = $env:HUIMA_TOOLS
    if (-not $raw) {
        Write-Host ''
        Write-Host '请选择要安装的软件：'
        Write-Host '  1  Claude Code   （在终端里使用的 AI 编程助手）'
        Write-Host '  2  Codex 桌面版  （OpenAI 的 AI 编程助手，有窗口界面）'
        Write-Host '  3  WorkBuddy     （腾讯的 AI 办公助手，有窗口界面）'
        $answer = Read-Host '输入编号后回车，例如 13 表示安装 1 和 3；直接回车表示全部安装'
        if (-not $answer -or -not $answer.Trim()) { $answer = '123' }
        $map = @{ '1' = 'claude'; '2' = 'codex'; '3' = 'workbuddy' }
        $raw = ($answer.ToCharArray() | ForEach-Object { $map["$_"] } | Where-Object { $_ }) -join ','
    }
    $tools = @($raw -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } |
        Where-Object { $_ -in @('claude', 'codex', 'workbuddy') } | Select-Object -Unique)
    if ($tools.Count -eq 0) { throw '没有选择任何软件，请重新运行并输入编号。' }
    return ,$tools
}

function Main {
    $transcriptStarted = $false
    $code = 1
    try {
        Write-Host '========================================================'
        Write-Host '                汇码 · 一键安装'
        Write-Host '========================================================'
        if ($env:CC_SETUP_MODE -and $env:CC_SETUP_MODE -ne '--no-pause') { throw '不支持此参数，直接双击运行即可。' }
        $architecture = $env:PROCESSOR_ARCHITECTURE
        if ($env:PROCESSOR_ARCHITEW6432) { $architecture = $env:PROCESSOR_ARCHITEW6432 }
        switch ($architecture) {
            'AMD64' { $architecture = 'x64' }
            'ARM64' { $architecture = 'arm64' }
            default { throw '本脚本需要 64 位 Windows（x64 或 ARM64），不支持 32 位系统。' }
        }
        $windows = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
        if ([int]$windows.CurrentBuildNumber -lt 17763) { throw '需要 Windows 10 1809 或更新版本；推荐 Windows 11。' }
        $tools = Get-Selection
        $script:WorkDir = Join-Path $env:LOCALAPPDATA ('HuimaSetup\logs\' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
        New-Item -ItemType Directory -Path $script:WorkDir -Force | Out-Null
        Start-Transcript -LiteralPath (Join-Path $script:WorkDir '安装日志.txt') -Force | Out-Null
        $transcriptStarted = $true
        # Avoid project-level .npmrc files in the folder where the CMD was downloaded.
        Set-Location -LiteralPath $script:WorkDir
        Write-Host '全程使用国内可访问的下载源，不需要科学上网。请保持联网。'
        Write-Host '已经装好的软件会自动跳过。预计需要几分钟到半小时。'
        Write-Host '如果 Windows 弹出授权窗口，请点击“是”。'
        Refresh-Path
        $winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($winget) { $script:Winget = $winget.Source }
        foreach ($tool in $tools) {
            switch ($tool) {
                'claude' { Install-ClaudeCode $architecture }
                'codex' { Install-CodexDesktop $architecture }
                'workbuddy' { Install-WorkBuddy }
            }
        }
        Write-Step '安装结果'
        $allOk = $true
        $codexCliOk = $script:Results.Contains('Codex 命令行版') -and $script:Results['Codex 命令行版'] -eq 'ok'
        foreach ($entry in $script:Results.GetEnumerator()) {
            switch ($entry.Value) {
                'ok' { Write-Host "  [ 完成 ] $($entry.Key)" -ForegroundColor Green }
                'manual' { Write-Host "  [需手动] $($entry.Key)：请在打开的官网下载安装" -ForegroundColor Yellow }
                default {
                    Write-Host "  [ 失败 ] $($entry.Key)" -ForegroundColor Red
                    # A failed desktop install is fine when the CLI fallback worked.
                    if (-not ($entry.Key -eq 'Codex 桌面版' -and $codexCliOk)) { $allOk = $false }
                }
            }
        }
        if ($script:Results.Contains('Codex 桌面版') -and $script:Results['Codex 桌面版'] -ne 'ok' -and $codexCliOk) {
            Write-Host '  Codex 已改用命令行版，可以正常使用。' -ForegroundColor Yellow
        }
        Write-Host ''
        Write-Host '下一步：回到使用手册，完成“4.2 一键配置”。' -ForegroundColor Cyan
        if ($allOk) { $code = 0 }
        else { Write-Host '有软件没装好：检查网络后重新双击本脚本即可，已装好的会自动跳过。' -ForegroundColor Yellow }
    } catch {
        Write-Host "`n安装未完成：$($_.Exception.Message)" -ForegroundColor Red
        Write-Host '请按提示处理后重新运行；仍有问题时，把下面的日志文件夹发给客服。'
    } finally {
        if ($script:WorkDir) { Write-Host "`n日志文件夹：$($script:WorkDir)" }
        if ($transcriptStarted) { Stop-Transcript | Out-Null }
    }
    return $code
}

exit (Main)
