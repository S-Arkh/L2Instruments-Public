param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$system=Join-Path $root 'Scryde'
if(Get-Process -Name 'ScrydeGame*' -ErrorAction SilentlyContinue){throw 'Close Scryde before observing the test copy'}
if((Get-FileHash "$system\Interface.u").Hash -ne '0eec3fc00817f8771663535745ebd810d873af1c1b9bf8df8b7ab126f1edc3de'){throw 'Original Interface.u required'}
if((Get-FileHash "$system\Interface.xdat").Hash -ne 'a1bf7b8bedc24df1a7ea8051f56dea62e97218883627cc350b5365bc7923c87a'){throw 'Original XDAT required'}
$report=Join-Path $root 'module-observation.json'
$result=[ordered]@{started=(Get-Date).ToString('o');system=$system;observations=@();error=$null}
try {
    Start-Process "$system\ScrydeGame.exe" -WorkingDirectory $system | Out-Null
    foreach($delay in @(20,40,40)) {
        Start-Sleep -Seconds $delay
        foreach($p in @(Get-Process -Name 'ScrydeGame*' -ErrorAction SilentlyContinue)) {
            $entry=[ordered]@{time=(Get-Date).ToString('o');pid=$p.Id;name=$p.ProcessName;title=$p.MainWindowTitle;modules=@();error=$null}
            try {$entry.modules=@($p.Modules | ForEach-Object {[pscustomobject]@{name=$_.ModuleName;path=$_.FileName}})}
            catch {$entry.error=$_.Exception.Message}
            $result.observations+= [pscustomobject]$entry
        }
        $result | ConvertTo-Json -Depth 6 | Set-Content $report -Encoding UTF8
    }
} catch {$result.error=$_.Exception.Message;throw}
finally {$result | ConvertTo-Json -Depth 6 | Set-Content $report -Encoding UTF8}
