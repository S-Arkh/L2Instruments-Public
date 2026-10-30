param(
    [string]$Python = 'python',
    [Parameter(Mandatory=$true)][string]$ClientSystem
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -B prepare.py --native-only
    if ($LASTEXITCODE) { throw 'Native preparation failed' }
    & cmake -S . -B build -G 'Visual Studio 17 2022' -A Win32
    if ($LASTEXITCODE) { throw 'CMake failed' }
    & cmake --build build --config Release
    if ($LASTEXITCODE) { throw 'Native build failed' }
    $run = Join-Path $PSScriptRoot "tests\native-$(Get-Date -Format yyyyMMdd-HHmmss-fff)"
    New-Item -ItemType Directory $run | Out-Null
    Copy-Item build\Release\ExtensionL2.dll, build\Release\texture_vm_probe.exe, build\Release\options_probe.exe, build\Release\frame_probe.exe, build\Release\exit_process.exe, build\Release\exit_fixture.dll $run
    Copy-Item build\Release\texture_layout_probe.exe $run
    Copy-Item build\Release\GraciaBrowserHost.exe, build\Release\ipc_frame_probe.exe $run
    Copy-Item ..\..\sdk\webview2\build\native\x86\WebView2Loader.dll $run
    $results = @()
    function Probe([string]$name, [string]$exe, [string]$arguments, [int]$timeout = 60000) {
        $info = New-Object Diagnostics.ProcessStartInfo
        $info.FileName = Join-Path $run $exe
        $info.Arguments = $arguments
        $info.WorkingDirectory = $run
        $info.UseShellExecute = $false
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $child = [Diagnostics.Process]::Start($info)
        $stdout = $child.StandardOutput.ReadToEndAsync()
        $stderr = $child.StandardError.ReadToEndAsync()
        $finished = $child.WaitForExit($timeout)
        if (!$finished) { $child.Kill() }
        $child.WaitForExit()
        $code = $child.ExitCode
        $stdout.Result | Set-Content "$run\$name.log"
        $stderr.Result | Set-Content "$run\$name.err"
        $child.Dispose()
        if (!$finished -or $code -ne 0) { throw "$name failed ($code): $run" }
        if ($name -eq 'exit' -and $stdout.Result -notmatch 'READY_FOR_EXIT') { throw 'Exit fixture did not obtain a frame' }
        [pscustomobject]@{ name=$name; exit_code=$code; finished=$finished }
    }
    $results += Probe 'options' 'options_probe.exe' ''
    Copy-Item inputs\Core.dll "$run\Core.dll"
    $results += Probe 'vm-manual' 'texture_vm_probe.exe' "`"$run\Core.dll`" `"$ClientSystem`" `"$run\ExtensionL2.dll`" manual"
    $results += Probe 'texture-layout' 'texture_layout_probe.exe' "`"$run\Core.dll`" `"$PSScriptRoot\inputs\Engine.dll`" `"$ClientSystem`""
    Copy-Item ..\..\..\dll\dist\profiles\Gracia_epilogue\Core.dll "$run\Core.dll" -Force
    $results += Probe 'vm-patched' 'texture_vm_probe.exe' "`"$run\Core.dll`" `"$ClientSystem`" `"$run\ExtensionL2.dll`" patched"
    $results += Probe 'frames' 'frame_probe.exe' ''
    if (Test-Path "$run\options.config") { Remove-Item "$run\options.config" }
    $results += Probe 'ipc-frames' 'ipc_frame_probe.exe' ''
    '{"browser":{"startPage":"http://127.0.0.1:9/"}}' | Set-Content "$run\options.config" -Encoding UTF8
    $results += Probe 'exit' 'exit_process.exe' 'exit_fixture.dll' 15000
    $results | ConvertTo-Json | Set-Content "$run\result.json" -Encoding UTF8
    [pscustomobject]@{
        profile='gracia_epilogue_0941cac5'; run=$run; tests=$results;
        extension_sha256=(Get-FileHash "$run\ExtensionL2.dll" -Algorithm SHA256).Hash.ToLower();
        browser_host_sha256=(Get-FileHash "$run\GraciaBrowserHost.exe" -Algorithm SHA256).Hash.ToLower();
        patched_core_sha256=(Get-FileHash "$run\Core.dll" -Algorithm SHA256).Hash.ToLower();
        engine_sha256=(Get-FileHash inputs\Engine.dll -Algorithm SHA256).Hash.ToLower()
    } | ConvertTo-Json -Depth 5 | Set-Content native-validation.json -Encoding UTF8
    $results | Format-Table
    Write-Host "Native host tests passed: $run. Engine layout fixture passed; game-owned UObject/Canvas needs a game test."
} finally { Pop-Location }
