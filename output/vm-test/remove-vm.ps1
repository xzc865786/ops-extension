# Removes the test VM, its disk and checkpoints, and the firewall rule created by create-vm.ps1.
# Run in an elevated PowerShell when testing is finished:
#   powershell -ExecutionPolicy Bypass -File remove-vm.ps1
param(
    [string]$VmName = 'HuimaTest',
    [string]$VmRoot = 'D:\HyperV'
)
$ErrorActionPreference = 'Stop'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请右键 PowerShell，选择“以管理员身份运行”，再执行本脚本。'
}
$vm = Get-VM -Name $VmName -ErrorAction SilentlyContinue
$vmDir = Join-Path $VmRoot $VmName
Write-Host "将删除：虚拟机 $VmName、它的全部检查点、文件夹 $vmDir，以及测试用的防火墙规则。"
if ((Read-Host '确认删除请输入 Y 并回车') -notmatch '^[Yy]$') { Write-Host '已取消。'; return }
if ($vm) {
    if ($vm.State -ne 'Off') { Stop-VM -VMName $VmName -TurnOff -Force }
    Remove-VM -VMName $VmName -Force
}
if (Test-Path -LiteralPath $vmDir) { Remove-Item -LiteralPath $vmDir -Recurse -Force }
Get-NetFirewallRule -DisplayName 'Huima manual test (Hyper-V VM only)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host '已清理完毕。' -ForegroundColor Green
