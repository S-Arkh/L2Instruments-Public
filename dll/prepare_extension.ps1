param(
    [string]$Destination = (Join-Path $PSScriptRoot ('work/prepared-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))),
    [string]$NativeDll = (Join-Path $PSScriptRoot 'build/Release/ExtensionL2.dll'),
    [string]$Launcher = (Join-Path $PSScriptRoot '../int64/dist/win32/ucc64.exe'),
    [string]$ClientCore = '',
    [string]$ClientSystem = '',
    [string]$ReferencePackage = ''
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ClientCore)) {
    throw 'Specify -ClientCore with the ORIGINAL Core.dll from the target client (do not use a Core from another client).'
}
$CompilerRoot = (Resolve-Path (Join-Path $PSScriptRoot '../int64')).Path
$Destination = [System.IO.Path]::GetFullPath($Destination)
$NativeDll = (Resolve-Path $NativeDll).Path
$Launcher = (Resolve-Path $Launcher).Path
$ClientCore = (Resolve-Path $ClientCore).Path
if ([string]::IsNullOrWhiteSpace($ClientSystem)) { $ClientSystem = Split-Path $ClientCore }
$ClientSystem = (Resolve-Path $ClientSystem).Path
if ([string]::IsNullOrWhiteSpace($ReferencePackage)) { $ReferencePackage = Join-Path $ClientSystem 'Interface.u' }
$ReferencePackage = (Resolve-Path $ReferencePackage).Path
if (Test-Path $Destination) { throw 'Choose a new destination for the DLL bundle.' }
$PreviousClientCore = $env:L2_CLIENT_CORE
Push-Location $PSScriptRoot
try {
    $env:L2_CLIENT_CORE = $ClientCore
    py -3 tools/check_core_dependencies.py $ClientSystem --core $ClientCore
    if ($LASTEXITCODE -ne 0) { throw 'The selected Core does not match the target client imports; see diagnostics above.' }
    $BindingTool = Join-Path (Split-Path $NativeDll) 'extension_bindings.exe'
    if (-not (Test-Path $BindingTool)) { throw 'Build extension_bindings.exe next to ExtensionL2.dll first.' }
    & $BindingTool $NativeDll ExtensionL2/Classes/ExtensionL2API.uc (Join-Path $Destination 'bindings.json')
    if ($LASTEXITCODE -ne 0) { throw 'UC binding generation failed' }
    $Workspace = Join-Path $Destination 'workspace'
    py -3 tools/prepare_uc.py $Workspace
    if ($LASTEXITCODE -ne 0) { throw 'UC workspace preparation failed' }
    py -3 (Join-Path $CompilerRoot 'tools/run_compile.py') (Join-Path $Workspace 'System') --launcher $Launcher
    if ($LASTEXITCODE -ne 0) { throw 'ExtensionL2.u compilation failed' }
    $Package = Join-Path $Workspace 'System/ExtensionL2.u'
    $Bytecode = Join-Path $Destination 'compiled-call.bin'
    py -3 tools/check_uc.py $Package --bindings-json (Join-Path $Destination 'bindings.json') --bytecode-output $Bytecode
    if ($LASTEXITCODE -ne 0) { throw 'ExtensionL2 bytecode verification failed' }
    $Client = Join-Path $Destination 'client'
    py -3 tools/patch_core.py $ClientCore (Join-Path $Client 'Core.dll')
    if ($LASTEXITCODE -ne 0) { throw 'Client Core patch creation failed' }
    Copy-Item $NativeDll (Join-Path $Client 'ExtensionL2.dll')
    py -3 (Join-Path $CompilerRoot 'tools/package_client.py') $Package (Join-Path $Client 'ExtensionL2.u') --like $ReferencePackage
    if ($LASTEXITCODE -ne 0) { throw 'ExtensionL2 packaging failed' }
    py -3 tools/validate_bundle.py $ClientCore $Client --system $ClientSystem --tools (Split-Path $NativeDll) --bytecode $Bytecode
    if ($LASTEXITCODE -ne 0) { throw 'Bundle loader/VM validation failed; inspect client/validation logs' }
    Write-Host "Prepared and validated client bundle: $Client"
} finally {
    $env:L2_CLIENT_CORE = $PreviousClientCore
    Pop-Location
}
