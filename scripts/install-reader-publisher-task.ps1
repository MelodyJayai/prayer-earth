$ErrorActionPreference = 'Stop'
$taskName = 'Prayer-Reader-Snapshot-Publish'
$runner = Join-Path $PSScriptRoot 'run-reader-publisher.ps1'
if (-not (Test-Path -LiteralPath $runner)) { throw 'Publisher runner was not found.' }
$action = New-ScheduledTaskAction `
    -Execute 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $runner + '"') `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$repeating = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3) -RepetitionInterval (New-TimeSpan -Minutes 15)
$startup = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($repeating, $startup) -Principal $principal -Settings $settings `
    -Description 'Publish validated public prayer reader snapshots every 15 minutes; keep the last deployed release if synchronization fails.' -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State, @{Name='LogonType'; Expression={$_.Principal.LogonType}}
