param(
    [ValidatePattern('^[A-Za-z_][A-Za-z_0-9]*$')]
    [string]$Package = 'Interface',
    [ValidateSet('', 'Gracia_152', 'HighFive_268', 'Japan_591', 'Korea_606')]
    [string]$Profile = '',
    [switch]$ClientSort,
    [switch]$ScopedEnumCasts,
    [ValidateSet('', 'korea290')]
    [string]$EnumProfile = ''
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$project = $root
if ($Profile) {
    $project = Join-Path $root "Profiles\$Profile"
    if ($Profile -in @('Japan_591', 'Korea_606')) {
        $ClientSort = $true
        $ScopedEnumCasts = $true
        # Both supplied profiles have the exact seven-member EL2ObjectType
        # sequence handled by this historically named compiler profile.
        $EnumProfile = 'korea290'
    }
}
$build = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$work = Join-Path $project "Work\$build"
$logdir = Join-Path $project "Logs\$build"
$system = Join-Path $work 'System'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$exitCode = 1
try {
    if ($Package -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
        throw 'Reserved package name.'
    }
    $sourceRoot = Join-Path $project 'Classes'
    $sources = @(Get-ChildItem -LiteralPath $sourceRoot -Filter '*.uc' -File -Recurse)
    if ($sources.Count -eq 0) { throw 'No .uc files found in Classes. See README_RU.txt.' }
    New-Item -ItemType Directory -Path $system, $logdir -Force | Out-Null
    Copy-Item -Path (Join-Path $root 'SDK\System\*') -Destination $system -Recurse
    if ($Profile) {
        # Shipped compiler-side profile dependencies, distinct from client originals.
        Get-ChildItem -LiteralPath (Join-Path $project 'CompilerDependencies') -Filter '*.u' -File |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $system -Force }
    }
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $project 'Dependencies') -File) {
        if ($file.Extension -ine '.u') { throw 'Dependencies accepts only .u packages.' }
        if (Test-Path -LiteralPath (Join-Path $system $file.Name)) {
            throw "Dependency would replace a bundled SDK file: $($file.Name)"
        }
        Copy-Item -LiteralPath $file.FullName -Destination $system
    }
    $names = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $project 'Dependencies.txt'))) {
        $name = $line.Trim()
        if (!$name -or $name.StartsWith('#')) { continue }
        if ($name -notmatch '^[A-Za-z_][A-Za-z_0-9]*$') { throw "Invalid dependency: $name" }
        if ($name -ieq $Package) { continue }
        if (@($names | Where-Object { $_ -ieq $name }).Count) { throw "Duplicate dependency: $name" }
        if (!(Test-Path -LiteralPath (Join-Path $system "$name.u"))) { throw "Missing dependency: $name.u" }
        $names.Add($name)
    }
    $names.Add($Package)
    $old = Join-Path $system "$Package.u"
    if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old }
    $classes = Join-Path $work "$Package\Classes"
    New-Item -ItemType Directory -Path $classes, (Join-Path $work "$Package\Inc") -Force | Out-Null
    foreach ($source in $sources) {
        $relative = $source.FullName.Substring($sourceRoot.Length).TrimStart('\', '/')
        $target = Join-Path $classes $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        [IO.File]::WriteAllText($target, [IO.File]::ReadAllText($source.FullName), [Text.Encoding]::Unicode)
    }
    $ini = "[Engine.Engine]`r`nEditorEngine=Editor.EditorEngine`r`n`r`n[Core.System]`r`nPaths=../System/*.u`r`n`r`n[Editor.EditorEngine]`r`nCacheSizeMegs=256`r`n"
    foreach ($name in $names) { $ini += "EditPackages=$name`r`n" }
    [IO.File]::WriteAllText((Join-Path $system 'UE2Runtime.ini'), $ini, [Text.Encoding]::ASCII)
    # Explicit settings make builds independent of inherited profile variables.
    Remove-Item Env:UCC64_CLIENT_ARRAY_SORT, Env:UCC64_CLIENT_ENUM_PROFILE, Env:UCC64_SCOPED_ENUM_CASTS -ErrorAction SilentlyContinue
    if ($ClientSort) { $env:UCC64_CLIENT_ARRAY_SORT = '1' }
    if ($ScopedEnumCasts) { $env:UCC64_SCOPED_ENUM_CASTS = '1' }
    if ($EnumProfile) { $env:UCC64_CLIENT_ENUM_PROFILE = $EnumProfile }
    $stdout = Join-Path $logdir 'compiler.log'
    $stderr = Join-Path $logdir 'stderr.log'
    Write-Host "Compiling $Package ($($sources.Count) source files)..."
    Write-Host "Logs: $logdir"
    $process = Start-Process -FilePath (Join-Path $root 'bin\ucc64.exe') -ArgumentList @('--system', ('"' + $system + '"'), 'make', '-NoBind', '-Silent') -WorkingDirectory $system -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -Wait
    Get-Content -LiteralPath $stdout
    if ((Get-Item -LiteralPath $stderr).Length) { Get-Content -LiteralPath $stderr }
    if ($process.ExitCode -ne 0) { throw "Compiler exit code: $($process.ExitCode)" }
    $artifact = Join-Path $system "$Package.u"
    if (!(Test-Path -LiteralPath $artifact)) { throw 'Compiler did not produce the requested package.' }
    $output = Join-Path $project 'Output'
    $archive = Join-Path $output $build
    New-Item -ItemType Directory -Path $archive -Force | Out-Null
    Copy-Item -LiteralPath $artifact -Destination $archive
    Copy-Item -LiteralPath $artifact -Destination (Join-Path $output "$Package.u") -Force
    $record = [ordered]@{status='PASS'; package=$Package; profile=$Profile; build=$build; sha256=(Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash; sources=$sources.Count; clientSort=[bool]$ClientSort; scopedEnumCasts=[bool]$ScopedEnumCasts; enumProfile=$EnumProfile}
    [IO.File]::WriteAllText((Join-Path $logdir 'result.json'), ($record | ConvertTo-Json), $utf8)
    Write-Host "PASS: $(Join-Path $output "$Package.u")"
    $exitCode = 0
} catch {
    New-Item -ItemType Directory -Path $logdir -Force | Out-Null
    $message = $_.Exception.Message
    [IO.File]::WriteAllText((Join-Path $logdir 'result.json'), (@{status='FAIL'; package=$Package; build=$build; error=$message} | ConvertTo-Json), $utf8)
    Write-Host "FAIL: $message" -ForegroundColor Red
    Write-Host 'An existing Output package, if any, belongs to a previous successful build.'
}
exit $exitCode
