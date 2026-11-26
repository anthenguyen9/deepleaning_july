param([ValidateSet('local','public','both')][string]$Mode = 'both')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$pythonExe = Join-Path $projectRoot 'instance/deploy-venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Missing web environment; install requirements_web.txt first.' }
$modes = if ($Mode -eq 'both') { @('local','public') } else { @($Mode) }
foreach ($serverMode in $modes) {
    $port = if ($serverMode -eq 'local') { 5001 } else { 5000 }
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        Write-Host "$serverMode already has a listener on port $port; left unchanged."
        continue
    }
    $process = Start-Process -FilePath $pythonExe -ArgumentList @('-m','scripts.serve','--mode',$serverMode) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot "instance/$serverMode`_server.out") -RedirectStandardError (Join-Path $projectRoot "instance/$serverMode`_server.err")
    $process.Id | Set-Content -LiteralPath (Join-Path $projectRoot "instance/$serverMode`_server.pid")
    Write-Host "Started $serverMode on port $port."
}
