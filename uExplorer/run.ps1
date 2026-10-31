param([string]$Python='', [switch]$CheckRuntime)
$ErrorActionPreference='Stop'
$launcher=Join-Path $PSScriptRoot 'launch.py'
if ($Python) {
    $candidates=@($Python)
} else {
    $candidates=@(
        (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
        (Join-Path $PSScriptRoot '..\interface_editor\.venv\Scripts\python.exe'),
        (Join-Path $PSScriptRoot '..\interface_editor\dist\windows\runtime\python.exe'),
        'python'
    )
}
$selected=''
foreach ($candidate in $candidates) {
    try {
        $probe=& $candidate -B $launcher --check-runtime 2>&1
        if ($LASTEXITCODE -eq 0) {
            $selected=$candidate
            break
        }
        if ($Python) {Write-Host ($probe -join "`n")}
    } catch {
        if ($Python) {Write-Host 'The requested Python could not be started.'}
    }
}
if (!$selected) {
    Write-Host 'uExplorer requires Python 3.10+ with working PySide6 (QtCore, QtGui, QtWidgets).'
    Write-Host 'From the uExplorer directory, create an environment and install dependencies:'
    Write-Host '  py -3 -m venv .venv'
    Write-Host '  .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
    Write-Host 'Then run .\run.cmd, or use .\run.ps1 -Python <python.exe>.'
    exit 1
}
if ($CheckRuntime) {
    Write-Host 'uExplorer runtime check passed.'
    Write-Host ($probe -join "`n")
    exit 0
}
& $selected -B $launcher
exit $LASTEXITCODE
