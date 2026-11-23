$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$outFile = Join-Path $root "data\youtube.cookies.txt"

Write-Host ""
Write-Host "TubeLocal — YouTube cookies setup"
Write-Host ""

# ---------- Preferred path: manual cookies.txt (works when Edge/Chrome DPAPI fails) ----------
Write-Host "RECOMMENDED (most reliable on Windows):"
Write-Host "  1) Install Edge/Chrome extension: 'Get cookies.txt LOCALLY'"
Write-Host "  2) Open https://www.youtube.com and make sure you are logged in"
Write-Host "  3) Click the extension → Export → save as:"
Write-Host "       $outFile"
Write-Host "  4) Restart the backend, then Fetch in the UI"
Write-Host ""

$browser = "edge"
if (Test-Path "$root\.env") {
    $line = Get-Content "$root\.env" | Where-Object { $_ -match '^\s*COOKIES_FROM_BROWSER\s*=' } | Select-Object -First 1
    if ($line -match '=\s*(.+)\s*$') { $browser = $Matches[1].Trim().ToLower() }
}

if ($browser -in @("", "none", "off", "false", "0")) {
    Write-Host "COOKIES_FROM_BROWSER is disabled. Use the manual export steps above."
    if (Test-Path $outFile) {
        Write-Host "Found existing cookies file: $outFile"
        exit 0
    }
    exit 0
}

Write-Host "Optional auto-export from browser '$browser' (often fails on modern Edge/Chrome)..."
Write-Host ""

$procsToStop = switch ($browser) {
    "chrome" { @("chrome") }
    "brave"  { @("brave") }
    "firefox" { @("firefox") }
    "chromium" { @("chrome", "chromium") }
    default  { @("msedge") }
}

$running = Get-Process -Name $procsToStop -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Closing $browser so the cookie DB unlocks..."
    Get-Process -Name $procsToStop -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
    Get-Process -Name $procsToStop -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Force -Path (Split-Path $outFile) | Out-Null

Set-Location "$root\backend"
$env:PYTHONPATH = "$root\backend"
& "$root\.venv\Scripts\python.exe" -c @"
from app.services.ytdlp_service import export_browser_cookies, YoutubeAccessError
try:
    path = export_browser_cookies('$browser')
    print('OK wrote', path)
except Exception as e:
    print('AUTO_EXPORT_FAILED:', e)
    raise SystemExit(2)
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Auto-export succeeded. Reopen the browser, restart backend, then Fetch."
    exit 0
}

Write-Host ""
Write-Host "Auto-export failed (common with Edge/Chrome DPAPI / app-bound encryption)."
Write-Host "Use the RECOMMENDED manual extension steps at the top of this script."
Write-Host "Save the file exactly as:"
Write-Host "  $outFile"
exit 2
