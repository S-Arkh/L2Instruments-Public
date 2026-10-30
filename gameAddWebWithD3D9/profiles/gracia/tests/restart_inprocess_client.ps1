param([Parameter(Mandatory=$true)][string]$Fixture,[int]$PreviousProcessId=0,[switch]$ChromiumLog)
$ErrorActionPreference='Stop'
$system=Join-Path (Resolve-Path $Fixture).Path 'system'
if($system -notlike '*\tests\inprocess-client-*\system'){throw 'Expected isolated fixture'}
if($PreviousProcessId) {
    $p=Get-Process -Id $PreviousProcessId -ErrorAction SilentlyContinue
    if($p){if($p.Path -ine "$system\L2.exe"){throw 'Unexpected process'};$p.Kill();$p.WaitForExit()}
}
$root=Split-Path $PSScriptRoot
Copy-Item "$root\build-inprocess\Release\ExtensionL2.dll" $system -Force
if($ChromiumLog){$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--enable-logging --v=1 --log-file=$system\inprocess-chromium.log"}
$p=Start-Process "$system\L2.exe" -WorkingDirectory $system -PassThru
Write-Host "Test PID: $($p.Id)"
Start-Sleep -Seconds 12
& "$PSScriptRoot\interact_inprocess_client.ps1" -ProcessId $p.Id -X 958 -Y 684 -Screenshot latest.png -WaitSeconds 2
& "$PSScriptRoot\interact_inprocess_client.ps1" -ProcessId $p.Id -X 958 -Y 684 -Screenshot latest.png -WaitSeconds 8
