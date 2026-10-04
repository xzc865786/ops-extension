# Run INSIDE the test VM, in an elevated PowerShell. Enables OpenSSH Server with key-only login
# for the Huima test key, reachable only from the Hyper-V host network.
$ErrorActionPreference = 'Stop'
$PublicKey = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKQzS8w51K0BTX60uBm4nsK9CJjSYfxpt4NMibI84hs2 huima-vm-test'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请右键开始按钮，选“终端(管理员)”，再运行这条命令。'
}

Write-Host '== 1/4 安装 OpenSSH 服务（Windows 自带组件，首次需联网下载，约 1-3 分钟）' -ForegroundColor Cyan
$capability = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*' | Select-Object -First 1
if (-not $capability) { throw '这个系统里找不到 OpenSSH 服务组件。' }
if ($capability.State -ne 'Installed') { Add-WindowsCapability -Online -Name $capability.Name | Out-Null }
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force | Out-Null

Write-Host '== 2/4 只允许密钥登录，并写入测试公钥' -ForegroundColor Cyan
$sshData = Join-Path $env:ProgramData 'ssh'
New-Item -ItemType Directory -Force -Path $sshData | Out-Null
Start-Service sshd  # first start generates sshd_config and host keys
$config = Join-Path $sshData 'sshd_config'
$text = [IO.File]::ReadAllText($config)
$text = [regex]::Replace($text, '(?m)^#?\s*PasswordAuthentication\s+\S+', 'PasswordAuthentication no')
if ($text -notmatch '(?m)^PasswordAuthentication no') { $text = "PasswordAuthentication no`r`n" + $text }
[IO.File]::WriteAllText($config, $text)
# Members of Administrators authenticate against this shared file; it must be readable only by admins and SYSTEM.
$keys = Join-Path $sshData 'administrators_authorized_keys'
[IO.File]::WriteAllText($keys, $PublicKey + "`r`n")
icacls.exe $keys /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null

Write-Host '== 3/4 防火墙：只允许本机（Hyper-V 主机网段）连接 22 端口' -ForegroundColor Cyan
Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue | Disable-NetFirewallRule
Get-NetFirewallRule -DisplayName 'Huima test SSH (host only)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'Huima test SSH (host only)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 `
    -RemoteAddress 172.16.0.0/12 -Profile Any | Out-Null

Write-Host '== 4/4 启动服务并设为开机自启' -ForegroundColor Cyan
Set-Service sshd -StartupType Automatic
Restart-Service sshd

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '172.*' } | Select-Object -First 1).IPAddress
Write-Host ''
Write-Host '设置完成，把下面两行告诉 Claude：' -ForegroundColor Green
Write-Host "  虚拟机 IP：$ip"
Write-Host "  用户名：$env:USERNAME"
