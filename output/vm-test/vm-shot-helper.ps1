# Screenshot helper for the manual: captures the HuimaTest VM console on request.
# Run in an elevated Windows PowerShell and leave the window open while taking screenshots:
#   powershell -ExecutionPolicy Bypass -File vm-shot-helper.ps1
# Claude drops "<name>.req" files into shots\requests; each one becomes shots\<name>.png.
# It only reads the VM's screen (Hyper-V thumbnail API); it runs nothing else and sends no input.
param([string]$VmName = 'HuimaTest')
$ErrorActionPreference = 'Stop'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请右键 PowerShell，选择“以管理员身份运行”，再执行本脚本。'
}
Add-Type -AssemblyName System.Drawing
$shots = Join-Path $PSScriptRoot 'shots'
$requests = Join-Path $shots 'requests'
New-Item -ItemType Directory -Force -Path $requests | Out-Null

function Save-VmScreen([string]$Path) {
    $ns = 'root\virtualization\v2'
    $vm = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$VmName'"
    if (-not $vm) { throw "找不到虚拟机 $VmName" }
    $settings = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Where-Object { $_.VirtualSystemType -eq 'Microsoft:Hyper-V:System:Realized' }
    $video = $vm.GetRelated('Msvm_VideoHead') | Select-Object -First 1
    $width = [int]$video.CurrentHorizontalResolution[0]
    $height = [int]$video.CurrentVerticalResolution[0]
    $service = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
    $image = $service.GetVirtualSystemThumbnailImage($settings, $width, $height).ImageData
    if (-not $image) { throw '没有取到画面（虚拟机未运行？）' }
    # The thumbnail API returns raw RGB565 pixels.
    $bitmap = New-Object System.Drawing.Bitmap -ArgumentList $width, $height, ([System.Drawing.Imaging.PixelFormat]::Format16bppRgb565)
    $rect = New-Object System.Drawing.Rectangle -ArgumentList 0, 0, $width, $height
    $data = $bitmap.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::WriteOnly, $bitmap.PixelFormat)
    [Runtime.InteropServices.Marshal]::Copy($image, 0, $data.Scan0, [Math]::Min($image.Length, $data.Stride * $height))
    $bitmap.UnlockBits($data)
    $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    return "${width}x${height}"
}

Write-Host "截图助手已启动：等待截图请求（$requests）。截图期间请保持本窗口打开，按 Ctrl+C 结束。" -ForegroundColor Green
while ($true) {
    foreach ($request in Get-ChildItem -LiteralPath $requests -Filter '*.req' -File -ErrorAction SilentlyContinue) {
        $name = $request.BaseName
        Remove-Item -LiteralPath $request.FullName -Force
        if ($name -notmatch '^[A-Za-z0-9_-]{1,64}$') { Write-Host "忽略不合法的名称：$name" -ForegroundColor Yellow; continue }
        try {
            $size = Save-VmScreen (Join-Path $shots "$name.png")
            Write-Host ("{0:HH:mm:ss} 已截图 {1}.png ({2})" -f (Get-Date), $name, $size)
        } catch {
            Write-Host ("{0:HH:mm:ss} 截图失败 {1}：{2}" -f (Get-Date), $name, $_.Exception.Message) -ForegroundColor Red
            Set-Content -LiteralPath (Join-Path $shots "$name.error.txt") -Value $_.Exception.Message -Encoding UTF8
        }
    }
    Start-Sleep -Milliseconds 300
}
