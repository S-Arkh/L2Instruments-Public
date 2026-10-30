param([string]$Python='python',[switch]$CompileOnly,[string]$OutputRoot=(Join-Path $PSScriptRoot 'out'))
$ErrorActionPreference='Stop'
$base=$PSScriptRoot
$source=Join-Path $PSScriptRoot 'profiles\high-five\Classes\BrowserWnd.uc'
foreach($profile in @('high-five','gracia')) {
    $root=Join-Path $PSScriptRoot "profiles\$profile"
    $run=Join-Path $PSScriptRoot ("work\$profile\"+(Get-Date -Format yyyyMMdd-HHmmss))
    New-Item -ItemType Directory $run | Out-Null
    Copy-Item "$root\workspace" "$run\workspace" -Recurse
    $workspace=Join-Path $run 'workspace'
    Copy-Item $source "$workspace\Interface\Classes\BrowserWnd.uc" -Force
    # Only remove the generated package from this newly created build copy.
    Remove-Item "$workspace\System\Interface.u" -ErrorAction SilentlyContinue
    & $Python -B "$base\tools\ue2\run_compile.py" "$workspace\System" --launcher "$base\toolchain\ucc64.exe"
    if($LASTEXITCODE){throw "UC compile failed: $profile"}
    if($CompileOnly){Write-Host "Compile-only passed: $profile";continue}
    $out=Join-Path $OutputRoot $profile
    New-Item -ItemType Directory -Force "$out\system" | Out-Null
    $bundle=if($profile -eq 'gracia'){"$root\result-inprocess\system"}else{"$root\result\system"}
    $names=@('ExtensionL2.dll','Interface.xdat','WebView2Loader.dll','options.config')
    if($profile -eq 'gracia'){$names+='Core.dll'}
    foreach($name in $names) {
        Copy-Item "$bundle\$name" "$out\system\$name" -Force
    }
    & $Python -B -c "import sys,runpy;sys.path.insert(0,r'$base\tools\ue2');sys.argv=['package_client',r'$workspace\System\Interface.u',r'$out\system\Interface.u','--like',r'$bundle\Interface.u','--replace'];runpy.run_module('package_client',run_name='__main__')"
    if($LASTEXITCODE){throw "Package failed: $profile"}
    $confirmation=Get-Content "$PSScriptRoot\reports\browser-options-validation.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    $tested=$confirmation.profiles.$profile
    $confirmed=$confirmation.user_confirmation.working -and
        ((Get-FileHash "$out\system\Interface.u").Hash -eq $tested.interface_sha256) -and
        ((Get-FileHash "$out\system\ExtensionL2.dll").Hash -eq $tested.extension_sha256)
    [pscustomobject]@{
        profile=$profile;feature='BrowserWnd.OpenBrowser(optional StartURL, optional HideControls)';
        compile_log="$workspace\compile.log";compiled=$true;game_tested=[bool]$confirmed;
        user_confirmed_working=[bool]$confirmed;confirmation_report="$PSScriptRoot\reports\browser-options-validation.json";
        files=@(Get-ChildItem "$out\system" -File | ForEach-Object {[pscustomobject]@{name=$_.Name;sha256=(Get-FileHash $_.FullName).Hash.ToLower()}})
    } | ConvertTo-Json -Depth 5 | Set-Content "$out\manifest.json" -Encoding UTF8
    Write-Host "Built: $out"
}
