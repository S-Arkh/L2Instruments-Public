param(
    [Parameter(Mandatory=$true)][ValidateSet('high-five','gracia')][string]$Profile,
    [Parameter(Mandatory=$true)][string]$ClientSystem,
    [int]$AttachPid = 0,
    [string]$BinaryDirectory = '',
    [string]$Report = ''
)
$ErrorActionPreference = 'Stop'
$system = (Resolve-Path $ClientSystem).Path
$project = [IO.Path]::GetFullPath("$PSScriptRoot\..\..")
$bin = if ($BinaryDirectory) { (Resolve-Path $BinaryDirectory).Path } else { Join-Path $project 'work\renderer-probe\Release' }
foreach ($name in @('renderer_attach.exe', 'renderer_probe.dll')) {
    if (!(Test-Path (Join-Path $bin $name) -PathType Leaf)) { throw "Build renderer_probe first; missing $name in $bin" }
}
if (!$Report) { $Report = Join-Path $project ("work\renderer-probe\renderer-device-$Profile-" + (Get-Date -Format 'yyyyMMdd-HHmmssfff') + '.json') }
$report = [IO.Path]::GetFullPath($Report)
New-Item -ItemType Directory -Force (Split-Path $report) | Out-Null
function ClientProcesses {
    @(Get-Process -Name 'l2','l2.bin' -ErrorAction SilentlyContinue | Where-Object { $_.Path -and (Split-Path $_.Path) -ieq $system })
}
if (!$AttachPid -and (ClientProcesses).Count) { throw 'Close the existing client before starting this controlled run' }
$state = [ordered]@{profile=$Profile;system=$system;started=(Get-Date).ToString('o');processes=@();error=$null}
$started = $false
try {
    if ($AttachPid) {
        $clients = @(ClientProcesses | Where-Object { $_.Id -eq $AttachPid })
    } else {
        Start-Process "$system\l2.exe" -WorkingDirectory $system | Out-Null
        $started = $true
        Start-Sleep -Seconds 25
        $clients = @(ClientProcesses | Where-Object { $_.ProcessName -match '^l2(\.bin)?$' })
    }
    if (!$clients.Count) { throw 'No L2 process found after launch' }
    foreach ($client in $clients) {
        & "$bin\renderer_attach.exe" $client.Id "$bin\renderer_probe.dll"
        $state.processes += [ordered]@{pid=$client.Id;name=$client.ProcessName;attach_exit=$LASTEXITCODE}
    }
    Start-Sleep -Seconds 15
    foreach ($entry in $state.processes) {
        $log = Join-Path $bin "renderer-$($entry.pid).log"
        $entry.log = if (Test-Path $log) { [IO.File]::ReadAllText($log) } else { $null }
    }
} catch { $state.error = $_.Exception.Message }
finally {
    if ($started) { ClientProcesses | Stop-Process -Force -ErrorAction SilentlyContinue }
    $state | ConvertTo-Json -Depth 5 | Set-Content $report -Encoding UTF8
}
if ($state.error) { throw $state.error }
$state | ConvertTo-Json -Depth 5
