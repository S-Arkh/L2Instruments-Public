param(
    [string]$Destination = (Join-Path $PSScriptRoot ('smoke-build-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))),
    [string]$Launcher = (Join-Path $PSScriptRoot 'build/Release/ucc64.exe')
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path $Launcher)) { throw "Launcher not found: $Launcher. Run build.ps1 or pass -Launcher." }
    $Launcher = (Resolve-Path $Launcher).Path
    if (-not (Test-Path (Join-Path (Split-Path $Launcher) 'Ucc64Bridge.dll'))) {
        throw 'Ucc64Bridge.dll must be next to the selected launcher'
    }
    if (Test-Path $Destination) { throw 'Use a new destination to compile the current smoke sources.' }
    py -3 tools/prepare_smoke.py $Destination
    if ($LASTEXITCODE -ne 0) { throw 'Smoke workspace preparation failed' }
    $System = Join-Path $Destination 'System'
    py -3 tools/run_compile.py $System --launcher $Launcher
    if ($LASTEXITCODE -ne 0) { throw 'Smoke compilation failed' }
    $Package = Join-Path $System 'Int64Smoke.u'
    py -3 tools/check_smoke.py $Package
    if ($LASTEXITCODE -ne 0) { throw 'Smoke bytecode verification failed' }
    Write-Host "Built and verified: $Package"
} finally {
    Pop-Location
}
