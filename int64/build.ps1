param(
    [ValidateSet('Debug', 'Release', 'RelWithDebInfo', 'MinSizeRel')]
    [string]$Configuration = 'Release',
    [string]$BuildDirectory = 'build'
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    cmake -S . -B $BuildDirectory -G 'Visual Studio 17 2022' -A Win32
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed' }
    cmake --build $BuildDirectory --config $Configuration
    if ($LASTEXITCODE -ne 0) { throw 'C++ build failed' }
    ctest --test-dir $BuildDirectory -C $Configuration --output-on-failure
    if ($LASTEXITCODE -ne 0) { throw 'C++ tests failed' }
    Write-Host "Built: $BuildDirectory/$Configuration (ucc64.exe, Ucc64Bridge.dll, int64_semantics_test.exe, client_native_probe.exe)"
} finally {
    Pop-Location
}
