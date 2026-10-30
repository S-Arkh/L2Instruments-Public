param([string]$Python='')
$ErrorActionPreference='Stop'
if (!$Python) {
    $embedded=Join-Path $PSScriptRoot '..\interface_editor\dist\windows\runtime\python.exe'
    if (Test-Path $embedded) {$Python=$embedded} else {$Python='python'}
}
& $Python -B (Join-Path $PSScriptRoot 'launch.py')
exit $LASTEXITCODE
