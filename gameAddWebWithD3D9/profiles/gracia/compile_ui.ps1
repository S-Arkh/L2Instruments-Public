param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -B ..\..\tools\ue2\run_compile.py workspace\System --launcher ..\..\toolchain\ucc64.exe
    if ($LASTEXITCODE -or !(Test-Path workspace\System\Interface.u)) { throw 'UI compilation did not produce Interface.u' }
} finally { Pop-Location }
