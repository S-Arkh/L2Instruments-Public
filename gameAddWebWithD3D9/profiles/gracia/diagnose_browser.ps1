param(
    [Parameter(Mandatory=$true)][string]$ClientSystem,
    [string]$CacheRoot = (Join-Path $env:TEMP 'l2-webview')
)
$ErrorActionPreference = 'Stop'
$ClientSystem = (Resolve-Path $ClientSystem).Path
if (!(Test-Path "$ClientSystem\Interface.u")) { throw 'Install result\system\Interface.u before this diagnostic run.' }
if (!(Test-Path "$ClientSystem\GraciaBrowserHost.exe")) { throw 'Install result\system\GraciaBrowserHost.exe beside ExtensionL2.dll.' }
if (Get-Process l2 -ErrorAction SilentlyContinue) { throw 'Close the running L2 client before this diagnostic run.' }
$run = Join-Path $PSScriptRoot ("tests\browser-diagnostic-" + (Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory $run | Out-Null
$profile = Join-Path $CacheRoot ([Guid]::NewGuid().ToString('N').Substring(0, 12))
New-Item -ItemType Directory -Path $profile | Out-Null
$log = Join-Path $run 'chromium.log'
$keys = @('WEBVIEW2_USER_DATA_FOLDER', 'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS')
$previous = @{}
foreach ($key in $keys) { $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process') }
try {
    [Environment]::SetEnvironmentVariable($keys[0], $profile, 'Process')
    $arguments = ($previous[$keys[1]] + ' --enable-logging --v=1 --log-file="' + $log + '"').Trim()
    [Environment]::SetEnvironmentVariable($keys[1], $arguments, 'Process')
    [pscustomobject]@{
        client=$ClientSystem; started=(Get-Date).ToString('o'); profile=$profile;
        arguments=$arguments; previous_environment=$previous;
        files=@(Get-Item "$ClientSystem\Core.dll", "$ClientSystem\ExtensionL2.dll", "$ClientSystem\GraciaBrowserHost.exe", "$ClientSystem\Interface.u", "$ClientSystem\Interface.xdat" | Get-FileHash -Algorithm SHA256)
    } | ConvertTo-Json -Depth 5 | Set-Content "$run\launch.json" -Encoding UTF8
    Write-Host "Open Browser once, then close the game. Diagnostic directory: $run"
    $process = Start-Process "$ClientSystem\L2.exe" -WorkingDirectory $ClientSystem -PassThru
    $process.WaitForExit()
    foreach ($name in @('web-texture.log','L2.log','browser-performance.json')) {
        if (Test-Path "$ClientSystem\$name") { Copy-Item "$ClientSystem\$name" $run }
    }
    Write-Host "Diagnostic complete: $run"
} finally {
    foreach ($key in $keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
