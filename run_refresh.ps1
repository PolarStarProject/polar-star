# Weekly refresh on a PC: new records, phone numbers, flights, rebuilt page. The same steps run on GitHub every week.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File .\run_refresh.ps1
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
$log = "data\refresh_log.txt"
"=== $(Get-Date -Format s) ===" | Add-Content $log
& $py pipeline\refresh_all.py @args 2>&1 | Tee-Object -FilePath $log -Append
exit $LASTEXITCODE
