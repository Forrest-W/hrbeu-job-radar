$ErrorActionPreference = 'Stop'

$radarRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'HRBEU Job Radar - Daily Incremental Update'
$updateBat = Join-Path $radarRoot 'update-latest.bat'
$logDir = Join-Path $radarRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/d /c `"$updateBat`""
$trigger = New-ScheduledTaskTrigger -Daily -At '02:15'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Daily incremental sync for HRBEU job radar.' -Force | Out-Null
Write-Output "Registered: $taskName"
Write-Output 'Schedule: daily at 02:15 local time'
Write-Output "Script: $updateBat"
