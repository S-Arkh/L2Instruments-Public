param([switch]$CompareOld)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$run = Join-Path $PSScriptRoot "exit-$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory $run | Out-Null
Copy-Item "$root\build\Release\exit_process.exe" $run
Copy-Item "$root\result\system\WebView2Loader.dll" $run
'{"browser":{"startPage":"http://127.0.0.1:9/"}}' | Set-Content "$run\options.config" -Encoding UTF8
$names = @('exit_fixture')
if ($CompareOld) { $names = @('exit_fixture_old', 'exit_fixture') }
$results = @()
foreach ($name in $names) {
    Copy-Item "$root\build\Release\$name.dll" $run
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = "$run\exit_process.exe"
    $info.Arguments = "$name.dll"
    $info.WorkingDirectory = $run
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $child = [Diagnostics.Process]::Start($info)
    $stdout = $child.StandardOutput.ReadToEndAsync()
    $stderr = $child.StandardError.ReadToEndAsync()
    $finished = $child.WaitForExit(15000)
    $code = $null
    if ($finished) { $child.WaitForExit(); $code = $child.ExitCode }
    else {
        # Terminate only the fixture process created above, never a game process.
        $child.Kill(); $child.WaitForExit()
    }
    $stdout.Result | Set-Content "$run\$name.log"
    $stderr.Result | Set-Content "$run\$name.err"
    $ready = $stdout.Result -match 'READY_FOR_EXIT'
    $results += [pscustomobject]@{ fixture=$name; ready=$ready; exited=$finished; exit_code=$code; elapsed_ms=$watch.ElapsedMilliseconds }
    $child.Dispose()
}
$results | ConvertTo-Json | Set-Content "$run\result.json" -Encoding UTF8
$results | Format-Table
$fixed = $results | Where-Object fixture -eq 'exit_fixture'
if (!$fixed.ready -or !$fixed.exited -or $fixed.exit_code -ne 0) { throw "Exit regression failed: $run" }
Write-Host 'PASS active WGC/WebView2 DLL exits without explicit Shutdown'
