param([ValidateSet('x64','Win32')][string]$Architecture='x64', [string]$Configuration='Release', [string]$Python='python')
$ErrorActionPreference='Stop'
$build=Join-Path $PSScriptRoot ("build-"+$Architecture)
$PythonExe = (& $Python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE) {throw 'Python with nlohmann_json is required'}
cmake -S $PSScriptRoot -B $build -G 'Visual Studio 17 2022' -A $Architecture "-DPython_EXECUTABLE=$PythonExe"
if ($LASTEXITCODE) {throw 'CMake configuration failed'}
cmake --build $build --config $Configuration
if ($LASTEXITCODE) {throw 'C++ build failed'}
cmake --install $build --config $Configuration --prefix $PSScriptRoot
if ($LASTEXITCODE) {throw 'Binary installation failed'}
Write-Host "Built $build\uExplorer.sln; DLL/CLI in bin. Use matching $Architecture Python."
