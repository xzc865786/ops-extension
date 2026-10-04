# Creates a clean Windows 11 Hyper-V VM for testing the Huima manual, plus a firewall rule that lets
# only Hyper-V VMs reach the local manual test server on port 18089.
# Run in an elevated PowerShell (Run as administrator):
#   powershell -ExecutionPolicy Bypass -File create-vm.ps1 -IsoPath "D:\Downloads\Win11_25H2_Chinese_Simplified_x64.iso"
param(
    [Parameter(Mandatory = $true)][string]$IsoPath,
    [string]$VmName = 'HuimaTest',
    [string]$VmRoot = 'D:\HyperV'
)
$ErrorActionPreference = 'Stop'

function Step([string]$Text) { Write-Host "`n== $Text" -ForegroundColor Cyan }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请右键 PowerShell，选择“以管理员身份运行”，再执行本脚本。'
}
if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) { throw "找不到 ISO 文件：$IsoPath" }
$existing = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if (-not (Get-VMSwitch -Name 'Default Switch' -ErrorAction SilentlyContinue)) { throw '没有找到 Hyper-V 的 Default Switch。' }

$vmDir = Join-Path $VmRoot $VmName
$vhd = Join-Path $vmDir "$VmName.vhdx"

if ($existing) {
    Step "虚拟机 $VmName 已经存在，跳过创建，直接启动"
} else {
Step "创建虚拟机 $VmName（第 2 代，4 核，内存 4-6 GB，硬盘 80 GB 动态扩展）"
New-Item -ItemType Directory -Force -Path $vmDir | Out-Null
New-VM -Name $VmName -Generation 2 -MemoryStartupBytes 4GB -NewVHDPath $vhd -NewVHDSizeBytes 80GB -SwitchName 'Default Switch' -Path $VmRoot | Out-Null
Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $true -MinimumBytes 2GB -StartupBytes 4GB -MaximumBytes 6GB
Set-VMProcessor -VMName $VmName -Count 4
# Clean revert points: no automatic checkpoints; take "干净系统" by hand after setup.
Set-VM -VMName $VmName -AutomaticCheckpointsEnabled $false -CheckpointType Standard

Step '挂载安装镜像，设置从光盘启动、安全启动和 TPM（Windows 11 必需）'
$dvd = Add-VMDvdDrive -VMName $VmName -Path $IsoPath -Passthru
Set-VMFirmware -VMName $VmName -FirstBootDevice $dvd -EnableSecureBoot On -SecureBootTemplate MicrosoftWindows
Set-VMKeyProtector -VMName $VmName -NewLocalKeyProtector
Enable-VMTPM -VMName $VmName
}

Step '防火墙：只允许 Hyper-V 虚拟机网段访问本机 18089 端口（手册测试服务）'
$ruleName = 'Huima manual test (Hyper-V VM only)'
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18089 `
    -RemoteAddress 172.16.0.0/12 -Profile Any | Out-Null

Step '启动虚拟机并打开窗口'
if ((Get-VM -Name $VmName).State -ne 'Running') {
    # Hyper-V cannot page VM memory out, so it needs the startup RAM free right now.
    $needMB = (Get-VMMemory -VMName $VmName).Startup / 1MB
    $freeMB = [math]::Floor((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB)
    if ($freeMB -lt $needMB + 300) {
        throw ("本机可用内存只有 {0:N1} GB，虚拟机启动需要 {1:N1} GB。请先关掉 Edge、Chrome、VS Code、QQ、微信等程序，再重新运行本脚本。" -f ($freeMB / 1024), ($needMB / 1024))
    }
    Start-VM -VMName $VmName
}
Start-Process vmconnect.exe -ArgumentList 'localhost', $VmName
Write-Host ''
Write-Host '窗口出现 “Press any key to boot from CD or DVD” 时，马上点进窗口按任意键。' -ForegroundColor Yellow
Write-Host '错过了就在 Hyper-V 窗口点“操作 → 重置”，再按一次。' -ForegroundColor Yellow
