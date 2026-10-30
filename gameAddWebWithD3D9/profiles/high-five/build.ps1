param([string]$Python = 'python', [Parameter(Mandatory=$true)][string]$ClientSystem)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$common = [IO.Path]::GetFullPath("$PSScriptRoot\..\..")
$base = Join-Path $common 'archive\addWeb'
Push-Location $PSScriptRoot
try {
    & $Python -B prepare.py
    if ($LASTEXITCODE) { throw 'Staging failed' }
    & cmake -S . -B build -G 'Visual Studio 17 2022' -A Win32
    if ($LASTEXITCODE) { throw 'CMake failed' }
    & cmake --build build --config Release
    if ($LASTEXITCODE) { throw 'Native compilation failed' }
    & build\Release\options_probe.exe
    if ($LASTEXITCODE) { throw 'JSON options probe failed' }
    & $Python -B "$common\tools\ue2\run_compile.py" workspace\System --launcher "$common\toolchain\ucc64.exe"
    if ($LASTEXITCODE) { throw 'UC compilation failed' }
    & $Python -B -c "import sys,runpy;sys.path.insert(0,r'$common\tools\ue2');sys.argv=['package_client','workspace/System/Interface.u','result/system/Interface.u','--like',r'$base\inputs\interface.u','--replace'];runpy.run_module('package_client',run_name='__main__')"
    if ($LASTEXITCODE) { throw 'Packaging failed' }
    Copy-Item build\Release\ExtensionL2.dll result\system\ExtensionL2.dll -Force
    Copy-Item "$common\sdk\webview2\build\native\x86\WebView2Loader.dll" result\system\WebView2Loader.dll -Force
    New-Item -ItemType Directory -Force tests\vm, tests\run | Out-Null
    Copy-Item "$base\inputs\Core.dll" tests\vm\Core.dll -Force
    Copy-Item result\system\ExtensionL2.dll tests\vm\ExtensionL2.dll -Force
    Copy-Item build\Release\texture_vm_probe.exe tests\vm\texture_vm_probe.exe -Force
    & tests\vm\texture_vm_probe.exe "$PSScriptRoot\tests\vm\Core.dll" $ClientSystem "$PSScriptRoot\tests\vm\ExtensionL2.dll" patched 2>&1 | Tee-Object tests\vm\probe.log
    if ($LASTEXITCODE) { throw 'Core VM probe failed' }
    $run = "tests\run-$(Get-Date -Format yyyyMMdd-HHmmss)"
    New-Item -ItemType Directory $run | Out-Null
    Copy-Item build\Release\frame_probe.exe "$run\frame_probe.exe"
    Copy-Item result\system\WebView2Loader.dll "$run\WebView2Loader.dll"
    & "$PSScriptRoot\$run\frame_probe.exe" 2>&1 | Tee-Object "$run\probe.log"
    if ($LASTEXITCODE) { throw 'Browser frame probe failed' }
    & "$PSScriptRoot\tests\test_exit.ps1"
    & $Python -B manifest.py
    if ($LASTEXITCODE) { throw 'Manifest generation failed' }
    Write-Host 'Browser texture built and host-tested; not installed in client.'
} finally { Pop-Location }
