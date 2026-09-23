param(
    [Parameter(Mandatory=$true)][string]$ExePath,
    [Parameter(Mandatory=$true)][string]$LocalAppDataPath
)

$ErrorActionPreference = 'Stop'
$resolvedExe = (Resolve-Path -LiteralPath $ExePath).Path
$resolvedBase = [System.IO.Path]::GetFullPath($LocalAppDataPath)
New-Item -ItemType Directory -Path $resolvedBase -Force | Out-Null
$env:LOCALAPPDATA = $resolvedBase
$startedAt = Get-Date
$process = Start-Process -FilePath $resolvedExe -PassThru -WindowStyle Hidden
$rootProcessId = $process.Id
$database = Join-Path $resolvedBase 'IvanSoprun\PropellerCalculatorProfessionalUA\propellers.db'
$ready = $false
for ($index = 0; $index -lt 300; $index++) {
    Start-Sleep -Milliseconds 200
    $process.Refresh()
    if ($process.HasExited) { break }
    if ((Test-Path -LiteralPath $database) -and ((Get-Item -LiteralPath $database).Length -gt 295000000)) {
        $ready = $true
        Start-Sleep -Seconds 3
        break
    }
}
$process.Refresh()
$alive = -not $process.HasExited
$windowHandle = if ($alive) { $process.MainWindowHandle } else { 0 }
if ($alive) {
    $process.CloseMainWindow() | Out-Null
    $processName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedExe)
    $instances = Get-Process -Name $processName -ErrorAction SilentlyContinue | Where-Object {
        $_.StartTime -ge $startedAt.AddSeconds(-1)
    }
    foreach ($instance in $instances) {
        Stop-Process -Id $instance.Id -Force -ErrorAction SilentlyContinue
    }
    $process.WaitForExit()
}
[pscustomobject]@{
    ready = $ready
    process_alive_after_start = $alive
    main_window_handle = $windowHandle
    exit_code = $process.ExitCode
    working_database = $database
    database_bytes = if (Test-Path -LiteralPath $database) { (Get-Item -LiteralPath $database).Length } else { 0 }
} | ConvertTo-Json -Depth 3
