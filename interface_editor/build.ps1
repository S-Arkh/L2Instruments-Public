param([string]$Configuration = 'Release')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 x64 first.' }
    }
    $Python = (Resolve-Path '.venv/Scripts/python.exe').Path
    & $Python -c "import struct; assert struct.calcsize('P') == 8, 'Use Python x64'"
    if ($LASTEXITCODE -ne 0) { throw 'Python x64 required' }
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & $Python -m cmake -S . -B build -G 'Visual Studio 17 2022' -A x64 "-DPython_EXECUTABLE=$Python"
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed; install VS2022 C++ tools' }
    & $Python -m cmake --build build --config $Configuration
    if ($LASTEXITCODE -ne 0) { throw 'C++ build failed' }
    & $Python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
} finally { Pop-Location }
