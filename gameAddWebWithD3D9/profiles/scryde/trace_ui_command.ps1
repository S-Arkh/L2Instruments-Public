$ErrorActionPreference='Stop'
$procmon=Join-Path $PSScriptRoot 'tools\procmon\Procmon64.exe'
if((Get-AuthenticodeSignature $procmon).Status -ne 'Valid'){throw 'Invalid Procmon signature'}
if(Get-Process -Name 'Procmon*' -ErrorAction SilentlyContinue){throw 'Existing Procmon session must be closed first'}
$clients=@(Get-Process -Name 'ScrydeGame.bin' -ErrorAction SilentlyContinue)
if($clients.Count -ne 1){throw 'Expected exactly one running game'}
$clientId=$clients[0].Id
$run=Join-Path $PSScriptRoot ('tests\ui-command-'+(Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory $run | Out-Null
$log=Join-Path $run 'command.pml'
$csv=Join-Path $run 'command.csv'
$state=[ordered]@{pid=$clientId;capture_started=$null;capture_finished=$null;export_complete=$false;error=$null}
$owned=$false
try {
 Start-Process $procmon -ArgumentList "/AcceptEula /Quiet /Minimized /NoFilter /BackingFile `"$log`" /Runtime 80" | Out-Null
 $owned=$true
 $ready=Start-Process $procmon -ArgumentList '/WaitForIdle' -PassThru
 if(!$ready.WaitForExit(20000)){throw 'Procmon readiness timeout'}
 $state.capture_started=(Get-Date).ToString('o')
 $state | ConvertTo-Json | Set-Content "$run\result.json" -Encoding UTF8
 $Host.UI.RawUI.WindowTitle='CAPTURE READY - enter ///ui once in game'
 Write-Host 'CAPTURE READY - switch to game and enter ///ui ONCE. Capturing for 60 seconds.' -ForegroundColor Green
 Start-Sleep -Seconds 60
 Start-Process $procmon -ArgumentList '/Terminate' -Wait
 $owned=$false
 $state.capture_finished=(Get-Date).ToString('o')
 Write-Host 'CAPTURE STOPPED - game can be closed. Exporting.'
 $export=Start-Process $procmon -ArgumentList "/AcceptEula /Quiet /OpenLog `"$log`" /SaveAs `"$csv`"" -Wait -PassThru
 if($export.ExitCode -ne 0 -or !(Test-Path $csv)){throw 'Export failed'}
 Import-Csv $csv | Where-Object {$_.'Process Name' -eq 'ScrydeGame.bin' -and $_.PID -eq "$clientId"} | Export-Csv "$run\scryde.csv" -NoTypeInformation -Encoding UTF8
 $state.export_complete=$true
} catch {$state.error=$_.Exception.Message;throw}
finally {
 if($owned){Start-Process $procmon -ArgumentList '/Terminate' -Wait}
 $state | ConvertTo-Json | Set-Content "$run\result.json" -Encoding UTF8
}
