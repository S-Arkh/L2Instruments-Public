param(
    [string]$Workspace = (Join-Path $PSScriptRoot 'workspace'),
    [string]$Launcher = (Join-Path $PSScriptRoot 'dist/win32/ucc64.exe'),
    [Parameter(Mandatory=$true)][string]$ReferencePackage
)
$ErrorActionPreference = 'Stop'
$ReferencePackage = (Resolve-Path $ReferencePackage).Path
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path $Launcher)) { throw "Launcher not found: $Launcher" }
    if (-not (Test-Path $Workspace)) {
        py -3 tools/prepare_interface.py $Workspace
        if ($LASTEXITCODE -ne 0) { throw 'Workspace preparation failed' }
    }
    py -3 tools/run_compile.py (Join-Path $Workspace 'System') --launcher $Launcher --rebuild-interface
    if ($LASTEXITCODE -ne 0) { throw 'Interface compilation failed; see workspace/compile.log' }
    py -3 tools/package_client.py (Join-Path $Workspace 'System/Interface.u') dist/client/Interface.u --like $ReferencePackage --replace
    if ($LASTEXITCODE -ne 0) { throw 'Package envelope validation failed' }
    New-Item -ItemType Directory -Force dist/client/plain | Out-Null
    Copy-Item (Join-Path $Workspace 'System/Interface.u') dist/client/plain/Interface.u -Force
    Write-Host 'Built: dist/client/Interface.u'
} finally {
    Pop-Location
}
