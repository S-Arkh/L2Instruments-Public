param([string]$Python='python')
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    & $Python -B prepare.py --native-only
    if($LASTEXITCODE){throw 'Preparation failed'}
    cmake -S . -B build-inprocess -G 'Visual Studio 17 2022' -A Win32 -DGRACIA_INPROCESS_BROWSER=ON
    if($LASTEXITCODE){throw 'Configuration failed'}
    cmake --build build-inprocess --config Release --target ExtensionL2 inprocess_compat_probe pipe_block_fixture exit_fixture_inprocess exit_process_pipe
    if($LASTEXITCODE){throw 'Build failed'}
    & "$PSScriptRoot\tests\test_pipe_compat.ps1"
    & "$PSScriptRoot\tests\test_inprocess_exit.ps1"
    $destination=Join-Path $PSScriptRoot 'result-inprocess\system'
    New-Item -ItemType Directory -Force $destination | Out-Null
    foreach($name in @('Core.dll','Interface.u','Interface.xdat','WebView2Loader.dll','options.config')) {
        Copy-Item "result\system\$name" $destination -Force
    }
    Copy-Item 'build-inprocess\Release\ExtensionL2.dll' $destination -Force
    if(Test-Path "$destination\GraciaBrowserHost.exe"){throw 'Unexpected helper in in-process output'}
    $files=@(Get-ChildItem $destination -File | ForEach-Object {
        [pscustomobject]@{name=$_.Name;sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower();bytes=$_.Length}
    })
    [pscustomobject]@{
        implementation='inprocess-webview2-pipe-compat';created=(Get-Date).ToString('o');files=$files;
        native_tests='passed';full_user_game_validation=$false;
        note='Separate candidate; old helper bundle and its game-validation remain unchanged.'
    } | ConvertTo-Json -Depth 5 | Set-Content 'result-inprocess\manifest.json' -Encoding UTF8
    Write-Host "In-process candidate: $destination (six files; no GraciaBrowserHost.exe)"
} finally {Pop-Location}
