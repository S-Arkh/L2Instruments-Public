param([string]$Configuration = 'Release')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    cmake -S . -B build -A Win32
    if ($LASTEXITCODE) { throw 'CMake configure failed' }
    cmake --build build --config $Configuration
    if ($LASTEXITCODE) { throw 'GPU probe build failed' }
    $run = "tests\run-$(Get-Date -Format yyyyMMdd-HHmmss)"
    New-Item -ItemType Directory -Path $run -Force | Out-Null
    Copy-Item "build\$Configuration\gpu_probe.exe" "$run\gpu_probe.exe"
    Copy-Item 'sdk\webview2\build\native\x86\WebView2Loader.dll' "$run\WebView2Loader.dll"
    & "$PSScriptRoot\$run\gpu_probe.exe" 2>&1 | Tee-Object "$run\probe.log"
    if ($LASTEXITCODE) { throw "GPU probe failed: $run" }
} finally { Pop-Location }
