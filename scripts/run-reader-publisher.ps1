$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$stateRoot = Join-Path $projectRoot '.reader-publish'
$pythonExe = 'C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$logFile = Join-Path $stateRoot 'publisher.log'
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 2MB) {
    Move-Item -LiteralPath $logFile -Destination ($logFile + '.previous') -Force
}
Set-Location -LiteralPath $projectRoot
& $pythonExe (Join-Path $PSScriptRoot 'deploy-reader-failover.py') 2>&1 | Out-File -LiteralPath $logFile -Append -Encoding utf8
exit $LASTEXITCODE
