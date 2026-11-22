param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [Parameter(Mandatory = $true)][string]$WorkspaceRoot
)

$ErrorActionPreference = 'Stop'
if (-not [System.IO.Path]::IsPathRooted($PythonPath)) { throw 'PythonPath must be absolute.' }
if (-not [System.IO.Path]::IsPathRooted($WorkspaceRoot)) { throw 'WorkspaceRoot must be absolute.' }
$python = (Resolve-Path -LiteralPath $PythonPath).Path
$workspace = (Resolve-Path -LiteralPath $WorkspaceRoot).Path
$collector = Join-Path $PSScriptRoot 'collect_sentiment.py'
$runner = Join-Path $PSScriptRoot 'run_sentiment_schedule.ps1'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'PythonPath must name an existing executable file.' }
if (-not (Test-Path -LiteralPath $workspace -PathType Container)) { throw 'WorkspaceRoot must name an existing directory.' }
if (-not (Test-Path -LiteralPath $collector -PathType Leaf)) { throw 'Sentiment collector is missing.' }
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Scheduled runner is missing.' }
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'Set the Windows local timezone to China Standard Time before installing this Beijing-time task.' }

$argument = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -PythonPath "{1}" -WorkspaceRoot "{2}"' -f $runner, $python, $workspace
$action = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $argument -WorkingDirectory $workspace
$triggers = @((New-ScheduledTaskTrigger -Daily -At '18:00'), (New-ScheduledTaskTrigger -Daily -At '20:00'))
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
# Diagnostics: schedule.log captures startup/import failures; market JSON records source issues.
# An offline host, missing Python, stale calendar or source outage cannot recreate a missed Legu day.
$description = 'A-share sentiment snapshot. Inspect research/evidence/sentiment/schedule.log, Task Scheduler last result and market/ daily JSON issues. Offline host, missing Python, stale calendar and source failures cannot be backfilled. Requires current user signed in.'
Register-ScheduledTask -TaskName 'stock-research-sentiment-market' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description $description -Force | Out-Null
Write-Output 'stock-research-sentiment-market registered for 18:00 and 20:00 China Standard Time.'
