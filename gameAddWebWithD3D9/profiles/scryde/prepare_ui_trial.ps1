param(
    [Parameter(Mandatory=$true)][string]$TargetSystem,
    [Parameter(Mandatory=$true)][string]$DonorSystem,
    [string]$TrialRoot='',
    [switch]$CopyResources
)
$ErrorActionPreference='Stop'
$target=(Resolve-Path -LiteralPath $TargetSystem).Path
$donor=(Resolve-Path -LiteralPath $DonorSystem).Path
$sourceRoot=Split-Path $target
$run=if($TrialRoot){[IO.Path]::GetFullPath($TrialRoot)}else{Join-Path $PSScriptRoot ('tests\ui-trial-'+(Get-Date -Format yyyyMMdd-HHmmss))}
if(Test-Path -LiteralPath $run){throw "Trial directory already exists: $run"}
New-Item -ItemType Directory $run | Out-Null
# Only the executable directory is copied. Resource directories are referenced;
# per-user output directories stay local to the fixture.
$system=Join-Path $run 'Scryde'
Copy-Item -LiteralPath $target -Destination $system -Recurse
foreach($name in @('Animations','ForceFeedback','L2text','MAPS','music','Sounds','StaticMeshes','SysTextures','Textures','Voice')) {
    $source=Join-Path $sourceRoot $name
    if(Test-Path -LiteralPath $source){
        if($CopyResources){
            & robocopy $source (Join-Path $run $name) /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
            if($LASTEXITCODE -ge 8){throw "Resource copy failed: $name (robocopy $LASTEXITCODE)"}
        }else{New-Item -ItemType Junction -Path (Join-Path $run $name) -Target $source | Out-Null}
    }
}
foreach($name in @('save','Screenshot','original-ui','replacement-ui')){New-Item -ItemType Directory (Join-Path $run $name) | Out-Null}
foreach($name in @('Interface.u','Interface.xdat')) {
    Copy-Item -LiteralPath (Join-Path $target $name) -Destination (Join-Path $run 'original-ui')
    Copy-Item -LiteralPath (Join-Path $donor $name) -Destination (Join-Path $run 'replacement-ui')
}
[pscustomobject]@{
    target=$target;donor=$donor;fixture_system=$system;current_ui='original';
    resources_copied=[bool]$CopyResources;
    original_ui=@(Get-ChildItem "$run\original-ui" -File | Get-FileHash -Algorithm SHA256);
    replacement_ui=@(Get-ChildItem "$run\replacement-ui" -File | Get-FileHash -Algorithm SHA256);
    note='Only the interface pair will be swapped after a baseline launch. No donor DLLs copied.'
} | ConvertTo-Json -Depth 5 | Set-Content "$run\fixture.json" -Encoding UTF8
Write-Host "UI trial: $run"
