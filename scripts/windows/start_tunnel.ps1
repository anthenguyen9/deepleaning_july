$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$tunnelExe = Join-Path $projectRoot 'instance/tools/cloudflared.exe'
if (-not (Test-Path -LiteralPath $tunnelExe)) { throw 'Missing instance/tools/cloudflared.exe' }
$pidFile = Join-Path $projectRoot 'instance/foodlens_tunnel.pid'
$originFile = Join-Path $projectRoot 'instance/tunnel_origin.txt'
if (Test-Path -LiteralPath $pidFile) {
    $previousPid = Get-Content -LiteralPath $pidFile -Raw
    $previous = Get-Process -Id ([int]$previousPid.Trim()) -ErrorAction SilentlyContinue
    if ($previous -and $previous.ProcessName -eq 'cloudflared') {
        Write-Host 'FoodLens tunnel is already running.'
        if (Test-Path -LiteralPath $originFile) { Get-Content -LiteralPath $originFile }
        exit 0
    }
}
$errorLog = Join-Path $projectRoot 'instance/foodlens_tunnel.err'
$process = Start-Process -FilePath $tunnelExe -ArgumentList @('tunnel','--url','http://127.0.0.1:5000','--protocol','http2','--no-autoupdate') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'instance/foodlens_tunnel.out') -RedirectStandardError $errorLog
$process.Id | Set-Content -LiteralPath $pidFile
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    $process.Refresh()
    if ($process.HasExited) { throw 'Tunnel exited; inspect instance/foodlens_tunnel.err' }
    $logText = Get-Content -LiteralPath $errorLog -Raw -ErrorAction SilentlyContinue
    if ($logText -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
        $origin = $Matches[0]
        $origin | Set-Content -LiteralPath $originFile -Encoding utf8
        Write-Host "Tunnel origin: $origin"
        Write-Host 'Update the existing foodlens-demo Worker origin if it changed; keep the Worker name unchanged.'
        exit 0
    }
}
throw 'Tunnel did not publish a URL within 30 seconds; inspect its log before restarting.'
