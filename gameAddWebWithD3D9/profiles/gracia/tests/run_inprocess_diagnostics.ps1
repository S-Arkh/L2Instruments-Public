param([Parameter(Mandatory=$true)][string]$ClientSystem)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$batch=Join-Path $PSScriptRoot ('inprocess-'+(Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory $batch | Out-Null
$cases=@(
    @{name='baseline';modules=@()},
    @{name='core-engine';modules=@('Core.dll','Engine.dll')},
    @{name='core-engine-nwindow';modules=@('Core.dll','Engine.dll','NWindow.dll')},
    @{name='core-engine-d3d';modules=@('Core.dll','Engine.dll','D3DDrv.dll')}
)
$results=@()
foreach($case in $cases) {
    $run=Join-Path $batch $case.name
    New-Item -ItemType Directory $run | Out-Null
    Copy-Item "$root\build-inprocess\Release\inprocess_diagnostic_probe.exe" $run
    Copy-Item "$root\..\..\sdk\webview2\build\native\x86\WebView2Loader.dll" $run
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=Join-Path $run 'inprocess_diagnostic_probe.exe'
    $info.Arguments='"'+$ClientSystem+'" '+($case.modules -join ' ')
    $info.WorkingDirectory=$run
    $info.UseShellExecute=$false
    $info.RedirectStandardOutput=$true
    $info.RedirectStandardError=$true
    $child=[Diagnostics.Process]::Start($info)
    $stdout=$child.StandardOutput.ReadToEndAsync();$stderr=$child.StandardError.ReadToEndAsync()
    $finished=$child.WaitForExit(90000)
    if(!$finished){$child.Kill();$child.WaitForExit()}
    $stdout.Result | Set-Content "$run\stdout.log"
    $stderr.Result | Set-Content "$run\stderr.log"
    $results+=[pscustomobject]@{name=$case.name;modules=$case.modules;finished=$finished;exit_code=$child.ExitCode;run=$run}
    $child.Dispose()
}
$results | ConvertTo-Json -Depth 5 | Set-Content "$batch\result.json"
$results | Format-Table
Write-Host "Diagnostics: $batch"
