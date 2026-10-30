$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$run=Join-Path $PSScriptRoot ('inprocess-exit-'+(Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory $run | Out-Null
Copy-Item "$root\build-inprocess\Release\exit_process_pipe.exe","$root\build-inprocess\Release\exit_fixture_inprocess.dll" $run
Copy-Item "$root\build-inprocess\fixtures\Release\integrity.dll" $run
Copy-Item "$root\..\..\sdk\webview2\build\native\x86\WebView2Loader.dll" $run
'{"browser":{"startPage":"http://127.0.0.1:9/"}}' | Set-Content "$run\options.config" -Encoding UTF8
$p=Start-Process "$run\exit_process_pipe.exe" -WorkingDirectory $run -PassThru
$finished=$p.WaitForExit(45000)
if(!$finished){$p.Kill();$p.WaitForExit()}
$code=$p.ExitCode
[pscustomobject]@{finished=$finished;exit_code=$code;ready=(Test-Path "$run\exit-ready.json")} | ConvertTo-Json | Set-Content "$run\result.json"
$p.Dispose()
if(!$finished -or $code -ne 0 -or !(Test-Path "$run\exit-ready.json")){throw "Active DLL exit test failed: $run"}
Write-Host "PASS active WebView/WGC process exit with pipe compatibility: $run"
