param([Parameter(Mandatory=$true)][string]$System)
$ErrorActionPreference='Stop'
$procmon=Join-Path $PSScriptRoot 'tools\procmon\Procmon64.exe'
$signature=Get-AuthenticodeSignature $procmon
if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation'){throw 'Microsoft signature validation failed'}
if(Get-Process -Name 'Procmon*','ScrydeGame*' -ErrorAction SilentlyContinue){throw 'Close Scryde and existing Procmon before this run'}
if((Get-FileHash "$system\Interface.u").Hash -ne '0eec3fc00817f8771663535745ebd810d873af1c1b9bf8df8b7ab126f1edc3de'){throw 'Original UI required'}
if((Get-FileHash "$system\Interface.xdat").Hash -ne 'a1bf7b8bedc24df1a7ea8051f56dea62e97218883627cc350b5365bc7923c87a'){throw 'Original XDAT required'}
$run=Join-Path $PSScriptRoot ('tests\startup-trace-'+(Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory $run | Out-Null
$log=Join-Path $run 'startup.pml'
$csv=Join-Path $run 'startup.csv'
$state=[ordered]@{run=$run;signature='Valid Microsoft';started=(Get-Date).ToString('o');capture_complete=$false;export_complete=$false;error=$null}
$owned=$false
try {
    Start-Process $procmon -ArgumentList "/AcceptEula /Quiet /Minimized /NoFilter /BackingFile `"$log`" /Runtime 100" | Out-Null
    $owned=$true
    $ready=Start-Process $procmon -ArgumentList '/WaitForIdle' -PassThru
    if(!$ready.WaitForExit(30000)){throw 'Procmon readiness timeout'}
    Start-Process "$system\ScrydeGame.exe" -WorkingDirectory $system | Out-Null
    Start-Sleep -Seconds 80
    Start-Process $procmon -ArgumentList '/Terminate' -Wait
    $owned=$false
    $state.capture_complete=$true
    $export=Start-Process $procmon -ArgumentList "/AcceptEula /Quiet /OpenLog `"$log`" /SaveAs `"$csv`"" -Wait -PassThru
    if($export.ExitCode -ne 0 -or !(Test-Path $csv)){throw 'Procmon export failed'}
    $state.export_complete=$true
    Import-Csv $csv | Where-Object {$_.'Process Name' -like 'ScrydeGame*'} | Export-Csv (Join-Path $run 'scryde.csv') -NoTypeInformation -Encoding UTF8
} catch {$state.error=$_.Exception.Message;throw}
finally {
    if($owned){Start-Process $procmon -ArgumentList '/Terminate' -Wait}
    $state | ConvertTo-Json | Set-Content (Join-Path $run 'result.json') -Encoding UTF8
}
