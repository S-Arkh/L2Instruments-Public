param(
    [string]$Python = 'python',
    [Parameter(Mandatory=$true)][string]$ExportedClasses,
    [Parameter(Mandatory=$true)][string]$ClientSystem
)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$common = [IO.Path]::GetFullPath("$PSScriptRoot\..\..")
Push-Location $PSScriptRoot
try {
    $snapshot = "recovered\build-$(Get-Date -Format yyyyMMdd-HHmmss-fff)"
    & $Python -B restore_sources.py $ExportedClasses --destination "$snapshot\normalized"
    if ($LASTEXITCODE) { throw 'Initial source recovery failed' }
    & $Python -B bytecode_sources.py $ExportedClasses --recovered "$snapshot\normalized" --destination "$snapshot\Classes" --all
    if ($LASTEXITCODE) { throw 'Bytecode source recovery failed' }
    & $Python -B prepare.py --classes "$snapshot\Classes"
    if ($LASTEXITCODE) { throw 'Profile/UI preparation failed' }
    & .\compile_ui.ps1 -Python $Python
    & $Python -B verify_recovery.py
    if ($LASTEXITCODE) { throw 'Recompiled Interface differs from the original CFG/expressions' }
    & .\build_native.ps1 -Python $Python -ClientSystem $ClientSystem
    & $Python -B -c "import sys,runpy;sys.path.insert(0,r'$common\tools\ue2');sys.argv=['package_client','workspace/System/Interface.u','result/system/Interface.u','--like','inputs/Interface.u','--replace'];runpy.run_module('package_client',run_name='__main__')"
    if ($LASTEXITCODE) { throw 'Interface packaging failed' }
    Copy-Item build\Release\ExtensionL2.dll result\system\ExtensionL2.dll -Force
    Copy-Item build\Release\GraciaBrowserHost.exe result\system\GraciaBrowserHost.exe -Force
    Copy-Item "$common\sdk\webview2\build\native\x86\WebView2Loader.dll" result\system\WebView2Loader.dll -Force
    & $Python -B manifest.py
    if ($LASTEXITCODE) { throw 'Bundle validation failed' }
    & $Python -B install.py --system $ClientSystem --check
    if ($LASTEXITCODE) { throw 'Target client profile check failed' }
    Write-Host 'Gracia browser kit built and host-verified in result/system. Not installed; game test pending.'
} finally { Pop-Location }
