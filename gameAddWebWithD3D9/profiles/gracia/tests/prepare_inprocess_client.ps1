param([Parameter(Mandatory=$true)][string]$ClientRoot)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$destination=Join-Path $PSScriptRoot ('inprocess-client-'+(Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory $destination | Out-Null
# System is a full independent copy; large read-only game asset directories are
# referenced by junctions. No installed client files are replaced.
foreach($entry in Get-ChildItem -LiteralPath $ClientRoot) {
    if($entry.Name -ieq 'system'){Copy-Item -LiteralPath $entry.FullName -Destination $destination -Recurse}
    elseif($entry.PSIsContainer){
        if($entry.Name -ieq 'interface'){continue}
        New-Item -ItemType Junction -Path (Join-Path $destination $entry.Name) -Target $entry.FullName | Out-Null
    }else{Copy-Item -LiteralPath $entry.FullName -Destination $destination}
}
$system=Join-Path $destination 'system'
Copy-Item "$root\build-inprocess\Release\ExtensionL2.dll" $system -Force
# Absence is intentional in this isolated fixture: prove the candidate cannot
# accidentally use the installed helper.
if(Test-Path "$system\GraciaBrowserHost.exe"){Remove-Item "$system\GraciaBrowserHost.exe"}
foreach($name in @('web-texture.log','inprocess-diagnostic.log','browser-performance.json')) {
    if(Test-Path "$system\$name"){Remove-Item "$system\$name"}
}
[pscustomobject]@{source=$ClientRoot;system=$system;extension_sha256=(Get-FileHash "$system\ExtensionL2.dll").Hash;game_tested=$false} |
    ConvertTo-Json | Set-Content "$destination\fixture.json"
Write-Host "Isolated client: $system"
