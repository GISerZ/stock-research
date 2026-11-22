param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [Parameter(Mandatory = $true)][string]$WorkspaceRoot
)

$ErrorActionPreference = 'Stop'
$collector = Join-Path $PSScriptRoot 'collect_sentiment.py'
$coverage = Join-Path $PSScriptRoot 'check_sentiment_coverage.py'
$logDir = Join-Path $WorkspaceRoot 'research\evidence\sentiment'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir 'schedule.log'
'[{0}] market collection' -f (Get-Date -Format o) | Out-File -FilePath $log -Append -Encoding utf8
try {
    & $PythonPath $collector --market --output-dir $WorkspaceRoot 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
    $collectorCode = $LASTEXITCODE
    if ($null -eq $collectorCode) { $collectorCode = 2 }
    'exit_code={0}' -f $collectorCode | Out-File -FilePath $log -Append -Encoding utf8
    '[{0}] market coverage' -f (Get-Date -Format o) | Out-File -FilePath $log -Append -Encoding utf8
    try {
        & $PythonPath $coverage --output-dir $WorkspaceRoot 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
        $coverageCode = $LASTEXITCODE
        if ($null -eq $coverageCode) { $coverageCode = 2 }
    }
    catch {
        $_ | Out-File -FilePath $log -Append -Encoding utf8
        $coverageCode = 2
    }
    'coverage_exit_code={0}' -f $coverageCode | Out-File -FilePath $log -Append -Encoding utf8
    if ($collectorCode -ne 0) { exit $collectorCode }
    exit $coverageCode
}
catch {
    $_ | Out-File -FilePath $log -Append -Encoding utf8
    $failureCode = 2
    if ($null -ne $collectorCode -and $collectorCode -ne 0) { $failureCode = $collectorCode }
    'exit_code={0}' -f $failureCode | Out-File -FilePath $log -Append -Encoding utf8
    exit $failureCode
}
