# Watch a WeChat "Save As" folder and re-run scripts/import-wechat-content.py
# after .jpg files stay unchanged for a few seconds.
# Resolution order matches resolve_source_directory in import-wechat-content.py:
# -Source, PRAYER_WECHAT_IMAGES, <repo>\WeChatImages\WeChatImages, then
# <repo>\..\WeChatImages. The daily workflow is documented in docs/content-import.md.
# This file is ASCII-only so Windows PowerShell 5.1 can parse it without a BOM.

[CmdletBinding()]
param(
    [string]$Source = "",
    [ValidateRange(1, 3600)]
    [int]$DebounceSeconds = 3,
    [switch]$ImportOnStart
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$importer = Join-Path $PSScriptRoot "import-wechat-content.py"
$logDir = Join-Path $projectRoot ".wechat-import"
$logFile = Join-Path $logDir "watch.log"
# A hidden scheduled task may have no console; keep going if the handle is missing.
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
} catch {
    Write-Warning "Console encoding was left unchanged."
}
$env:PYTHONIOENCODING = "utf-8"

function Write-WatchLog {
    param([string]$Message)
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 2MB) {
        Move-Item -LiteralPath $logFile -Destination ($logFile + ".previous") -Force
    }
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logFile -Value ("[{0}] {1}" -f $stamp, $Message) -Encoding UTF8
}

function Resolve-WechatImageSource {
    param([string]$Explicit)
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        if (-not (Test-Path -LiteralPath $Explicit -PathType Container)) {
            throw "Source folder not found (-Source): $Explicit"
        }
        return (Resolve-Path -LiteralPath $Explicit).ProviderPath
    }
    $fromEnv = $env:PRAYER_WECHAT_IMAGES
    if (-not [string]::IsNullOrWhiteSpace($fromEnv)) {
        if (-not (Test-Path -LiteralPath $fromEnv -PathType Container)) {
            throw "Source folder not found (PRAYER_WECHAT_IMAGES): $fromEnv"
        }
        return (Resolve-Path -LiteralPath $fromEnv).ProviderPath
    }
    $legacy = Join-Path (Join-Path $projectRoot "WeChatImages") "WeChatImages"
    $sibling = Join-Path (Split-Path -Parent $projectRoot) "WeChatImages"
    foreach ($candidate in @($legacy, $sibling)) {
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            return (Resolve-Path -LiteralPath $candidate).ProviderPath
        }
    }
    throw "Source folder not found. Pass -Source, set PRAYER_WECHAT_IMAGES, or create $legacy or $sibling."
}

function Get-PythonLauncher {
    # PrefixArg is a single string. PowerShell unwraps one-element arrays stored in hashtables.
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Executable = $py.Source; PrefixArg = "-3" }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Executable = $python.Source; PrefixArg = "" }
    }
    throw "Python 3 was not found on PATH. Install Python, then retry (expected py -3 or python)."
}

function Test-SameText {
    param($Left, $Right)
    return [string]::Equals([string]$Left, [string]$Right, [System.StringComparison]::Ordinal)
}

function Get-JpegSnapshotText {
    param([string]$Folder)
    $rows = @(Get-ChildItem -LiteralPath $Folder -Filter "*.jpg" -File | Sort-Object -Property Name)
    if ($rows.Count -eq 0) {
        return ""
    }
    return (($rows | ForEach-Object { $_.Name + "`t" + $_.Length + "`t" + $_.LastWriteTimeUtc.Ticks }) -join "`n")
}

function Invoke-WechatImport {
    param(
        [string]$Folder,
        [hashtable]$Launcher
    )
    Write-Host ("Importing {0}" -f $Folder)
    Write-WatchLog ("import start: {0}" -f $Folder)
    # Continue: with Stop, stderr redirected through 2>&1 can abort before LASTEXITCODE is read.
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if ([string]::IsNullOrEmpty($Launcher.PrefixArg)) {
        $pythonOutput = & $Launcher.Executable $importer --source $Folder 2>&1
    } else {
        $pythonOutput = & $Launcher.Executable $Launcher.PrefixArg $importer --source $Folder 2>&1
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorAction
    $text = ($pythonOutput | Out-String).TrimEnd()
    if ($text) {
        Write-Host $text
        Write-WatchLog $text
    }
    if ($code -ne 0) {
        throw "import-wechat-content.py exited with code $code"
    }
    Write-WatchLog "import finished"
}

$resolved = Resolve-WechatImageSource -Explicit $Source
$launcher = Get-PythonLauncher
Set-Location -LiteralPath $projectRoot
Write-Host ("Watching {0} (debounce {1}s). Press Ctrl+C to stop." -f $resolved, $DebounceSeconds)
Write-Host ("Log: {0}" -f $logFile)
Write-WatchLog ("watching {0}" -f $resolved)

$lastSnapshot = ""
$pendingSnapshot = $null
$stableSince = $null
$retryAfter = [datetime]::MinValue

if ($ImportOnStart) {
    $existing = Get-JpegSnapshotText -Folder $resolved
    if ([string]::IsNullOrEmpty($existing)) {
        Write-Warning "No .jpg files in $resolved; startup import skipped."
        Write-WatchLog "startup import skipped; no .jpg files"
        $lastSnapshot = $existing
    } else {
        try {
            Invoke-WechatImport -Folder $resolved -Launcher $launcher
            $lastSnapshot = Get-JpegSnapshotText -Folder $resolved
        } catch {
            Write-Warning $_.Exception.Message
            Write-WatchLog ("startup import failed: " + $_.Exception.Message)
            $lastSnapshot = ""
            $retryAfter = (Get-Date).AddSeconds(30)
        }
    }
} else {
    $lastSnapshot = Get-JpegSnapshotText -Folder $resolved
    Write-Host "Existing files stay as they are until the folder changes. Pass -ImportOnStart to import them now."
}

while ($true) {
    Start-Sleep -Seconds 1
    $snapshot = Get-JpegSnapshotText -Folder $resolved
    if (Test-SameText $snapshot $lastSnapshot) {
        $pendingSnapshot = $null
        $stableSince = $null
        continue
    }
    if (-not (Test-SameText $snapshot $pendingSnapshot)) {
        $pendingSnapshot = $snapshot
        $stableSince = Get-Date
        Write-Host "Change detected; waiting ${DebounceSeconds}s for files to settle."
        continue
    }
    if (((Get-Date) - $stableSince).TotalSeconds -lt $DebounceSeconds) {
        continue
    }
    if ((Get-Date) -lt $retryAfter) {
        continue
    }
    try {
        if ([string]::IsNullOrEmpty($snapshot)) {
            Write-Warning "No .jpg files in $resolved; import skipped."
            Write-WatchLog "import skipped; no .jpg files"
            $lastSnapshot = $snapshot
        } else {
            Invoke-WechatImport -Folder $resolved -Launcher $launcher
            $lastSnapshot = Get-JpegSnapshotText -Folder $resolved
        }
        $pendingSnapshot = $null
        $stableSince = $null
        $retryAfter = [datetime]::MinValue
    } catch {
        Write-Warning $_.Exception.Message
        Write-WatchLog ("import failed: " + $_.Exception.Message)
        $retryAfter = (Get-Date).AddSeconds(30)
        $stableSince = Get-Date
    }
}
