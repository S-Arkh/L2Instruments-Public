$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$batch=Join-Path $PSScriptRoot ('pipe-compat-'+(Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory $batch | Out-Null
$results=@()
foreach($enabled in @(0,1)) {
    $run=Join-Path $batch "enabled-$enabled"
    New-Item -ItemType Directory $run | Out-Null
    Copy-Item "$root\build-inprocess\Release\inprocess_compat_probe.exe" $run
    Copy-Item "$root\build-inprocess\fixtures\Release\integrity.dll" $run
    Copy-Item "$root\..\..\sdk\webview2\build\native\x86\WebView2Loader.dll" $run
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=Join-Path $run 'inprocess_compat_probe.exe'
    $info.Arguments='"'+$run+'" integrity.dll'
    $info.WorkingDirectory=$run;$info.UseShellExecute=$false
    $info.EnvironmentVariables['GRACIA_WEBVIEW_PIPE_COMPAT']="$enabled"
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $p=[Diagnostics.Process]::Start($info)
    $stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync()
    $finished=$p.WaitForExit(90000)
    if(!$finished){$p.Kill();$p.WaitForExit()}
    $stdout.Result | Set-Content "$run\stdout.log";$stderr.Result | Set-Content "$run\stderr.log"
    $results+=[pscustomobject]@{enabled=$enabled;finished=$finished;exit_code=$p.ExitCode;run=$run}
    $p.Dispose()
}
$results | ConvertTo-Json | Set-Content "$batch\result.json"
$results | Format-Table
if(!$results[0].finished -or $results[0].exit_code -eq 0 -or !$results[1].finished -or $results[1].exit_code -ne 0){throw "Pipe regression failed: $batch"}
$isolation=Get-Content "$batch\enabled-1\pipe-isolation.json" | ConvertFrom-Json
if(!$isolation.ordinary_pipe_still_blocked){throw 'Ordinary pipes changed'}
Write-Host "PASS: blocked baseline, full frame/input suite with compatibility, ordinary pipes still blocked: $batch"
