# Registers the weekly refresh in Windows Task Scheduler (Mondays 06:00). Run once.
$script = Join-Path $PSScriptRoot "run_refresh.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 6am
Register-ScheduledTask -TaskName "DetentionMapRefresh" -Action $action -Trigger $trigger -Description "Refresh detention records and phone numbers, rebuild the page" -Force
