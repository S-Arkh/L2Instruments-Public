param([ValidateSet('Debug', 'Release', 'RelWithDebInfo')][string]$Configuration = 'Release')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    cmake -S . -B build -G 'Visual Studio 17 2022' -A Win32
    if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
    cmake --build build --config $Configuration
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    cmake --build build --config $Configuration --target generate_native_uc
    if ($LASTEXITCODE -ne 0) { throw 'UC binding generation failed' }
    Write-Host "Built: build/$Configuration/ExtensionL2.dll and tools; generated ExtensionL2/Classes/ExtensionL2API.uc"
} finally {
    Pop-Location
}
