# Crops, cleans and compresses the raw VM screenshots into frontend/manual/assets/screenshots.
# Run with Windows PowerShell (System.Drawing):  powershell -ExecutionPolicy Bypass -File process-shots.ps1
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$src = Join-Path $PSScriptRoot 'shots'
$dst = Resolve-Path (Join-Path $PSScriptRoot '..\..\frontend\manual\assets\screenshots')

# The "激活 Windows" watermark sits at the bottom-right of every 1280x800 capture.
$watermark = @{ X = 1020; Y = 668; W = 205; H = 50 }

# name = output file; crop = x,y,w,h on the 1280x800 source; clone = cover the watermark with the
# pixels 210px to its left (only where that band is plain background); cover = rects filled with a colour.
$jobs = @(
    @{ src = 's02-edge-keep';           name = 'quick-edge-keep';        crop = 860, 40, 392, 200 }
    @{ src = 's03-open-file-warning';   name = 'quick-open-file-warning'; crop = 417, 321, 466, 370 }
    @{ src = 's05-uac-node';            name = 'quick-uac-node';         crop = 413, 225, 458, 351 }
    @{ src = 's06-install-result';      name = 'quick-install-result';   crop = 55, 55, 1112, 615 }
    @{ src = 's08-config-result';       name = 'quick-config-result';    crop = 101, 92, 1112, 620; clone = $true }
    @{ src = 's09-address-cmd';         name = 'quick-address-cmd';      crop = 260, 88, 785, 590 }
    @{ src = 's10-claude-trust';        name = 'quick-claude-trust';     crop = 55, 55, 1112, 470 }
    @{ src = 's10b-claude-reply';       name = 'quick-claude-reply';     crop = 55, 55, 1112, 500 }
    @{ src = 's10c-claude-model';       name = 'quick-claude-model';     crop = 55, 55, 1112, 580 }
    @{ src = 's12-codex-desktop';       name = 'quick-codex-desktop';    crop = 98, 75, 1088, 603 }
    @{ src = 's11-workbuddy-model';     name = 'quick-workbuddy-model';  crop = 370, 20, 800, 420 }
    @{ src = 's11b-workbuddy-reply';    name = 'quick-workbuddy-reply';  crop = 305, 10, 936, 320 }
    @{ src = 's13-workbuddy-add-model'; name = 'ccs-workbuddy-add-model'; crop = 322, 85, 640, 583 }
    @{ src = 's14-ccswitch-main';       name = 'ccs-main';               crop = 62, 52, 900, 300 }
    @{ src = 's15-browser-open-ccswitch'; name = 'ccs-browser-open';     crop = 418, 78, 448, 158; cover = @(@{ X = 432; Y = 136; W = 135; H = 22; Color = 'White' }) }
    @{ src = 's16-ccswitch-import-preview'; name = 'ccs-import-preview'; crop = 262, 119, 500, 528 }
    @{ src = 's17b-ccswitch-card-hover'; name = 'ccs-card-hover';        crop = 62, 52, 900, 310 }
    @{ src = 's18a-ccswitch-preset';    name = 'ccs-preset';             crop = 26, 30, 1232, 640; clone = $true }
    @{ src = 's18-ccswitch-add-claude'; name = 'ccs-claude-form';        crop = 26, 30, 1232, 636 }
    @{ src = 's18b-ccswitch-claude-advanced'; name = 'ccs-claude-models'; crop = 50, 90, 1180, 560 }
    @{ src = 's18c-ccswitch-claude-fallback'; name = 'ccs-claude-fallback'; crop = 50, 155, 1180, 115 }
    @{ src = 's19-ccswitch-add-codex';  name = 'ccs-codex-form';         crop = 26, 30, 1232, 650; clone = $true }
    @{ src = 's19b-ccswitch-codex-advanced'; name = 'ccs-codex-advanced'; crop = 50, 140, 1180, 230 }
    @{ src = 's20-claude-onboarding-theme'; name = 'ccs-claude-theme';   crop = 78, 84, 1113, 616; clone = $true }
)

$jpeg = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object MimeType -eq 'image/jpeg'
$params = New-Object System.Drawing.Imaging.EncoderParameters(1)
$params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]86)
$maxWidth = 1000

foreach ($job in $jobs) {
    $path = Join-Path $src "$($job.src).png"
    if (-not (Test-Path $path)) { Write-Host "跳过（没有原图）：$($job.src)" -ForegroundColor Yellow; continue }
    $image = [System.Drawing.Bitmap]::FromFile($path)
    try {
        $canvas = New-Object System.Drawing.Bitmap($image.Width, $image.Height)
        $g = [System.Drawing.Graphics]::FromImage($canvas)
        $g.DrawImage($image, 0, 0, $image.Width, $image.Height)
        if ($job.clone) {
            $from = New-Object System.Drawing.Rectangle(($watermark.X - 210), $watermark.Y, $watermark.W, $watermark.H)
            $to = New-Object System.Drawing.Rectangle($watermark.X, $watermark.Y, $watermark.W, $watermark.H)
            $g.DrawImage($image, $to, $from, [System.Drawing.GraphicsUnit]::Pixel)
        }
        foreach ($rect in @($job.cover)) {
            if (-not $rect) { continue }
            $color = if ($rect.Color.StartsWith('#')) { [System.Drawing.ColorTranslator]::FromHtml($rect.Color) } else { [System.Drawing.Color]::FromName($rect.Color) }
            $brush = New-Object System.Drawing.SolidBrush($color)
            $g.FillRectangle($brush, $rect.X, $rect.Y, $rect.W, $rect.H)
            $brush.Dispose()
        }
        $g.Dispose()
        $x, $y, $w, $h = $job.crop
        $scale = [Math]::Min(1.0, $maxWidth / $w)
        $outW = [int][Math]::Round($w * $scale); $outH = [int][Math]::Round($h * $scale)
        $out = New-Object System.Drawing.Bitmap($outW, $outH)
        $g2 = [System.Drawing.Graphics]::FromImage($out)
        $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g2.DrawImage($canvas, (New-Object System.Drawing.Rectangle(0, 0, $outW, $outH)), (New-Object System.Drawing.Rectangle($x, $y, $w, $h)), [System.Drawing.GraphicsUnit]::Pixel)
        $g2.Dispose()
        $target = Join-Path $dst "$($job.name).jpg"
        $out.Save($target, $jpeg, $params)
        $out.Dispose(); $canvas.Dispose()
        Write-Host ("{0,-28} {1}x{2}  {3:N0} KB" -f $job.name, $outW, $outH, ((Get-Item $target).Length / 1KB))
    } finally { $image.Dispose() }
}
