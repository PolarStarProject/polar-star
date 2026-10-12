# Flights backfill to 1 January 2024. Newest day first. Safe to stop (Ctrl+C) and run again: finished days are skipped.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File .\run_flights_backfill.ps1
# Optional: a different start date     -Since 2025-01-01
#           a different download folder  -Work D:\adsb_tmp     (needs about 10 GB free; each day is deleted once read)
param([string]$Since = "2024-01-01", [string]$Work = "")
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "No .venv found in $PSScriptRoot. Create it first (see README)."; exit 1 }
if ($Work -eq "") { $Work = Join-Path $PSScriptRoot "data\flights\tmp" }
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$env:ADSB_WORK = $Work
$free = 999
try { $free = [math]::Round((Get-PSDrive -Name (Split-Path -Qualifier (Resolve-Path $Work).Path).TrimEnd(":")).Free / 1GB, 1) } catch { Write-Host "Could not measure free space; continuing." }
Write-Host "Download folder: $Work  ($free GB free)"
if ($free -lt 10) { Write-Host "Less than 10 GB free there. Free some space or pass -Work with another drive."; exit 1 }
$log = "data\flights_backfill_log.txt"
"=== started $(Get-Date -Format s), since $Since ===" | Add-Content $log
# Progress goes to the screen and to the log.
& $py -u pipeline\flights.py --since $Since 2>&1 | Tee-Object -FilePath $log -Append
"=== stopped $(Get-Date -Format s) ===" | Add-Content $log
Write-Host "Rebuilding the page with what has been read so far..."
& $py pipeline\build_site.py 2>&1 | Tee-Object -FilePath $log -Append
Write-Host "Done. Run this again any time to continue. Log: $log"
