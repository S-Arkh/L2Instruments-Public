param([Parameter(Mandatory=$true)][string]$System,
      [Parameter(Mandatory=$true)][string]$Test,
      [string[]]$Cases=@('baseline','relocated'))
$ErrorActionPreference = 'Stop'
$procmon = Join-Path $PSScriptRoot 'tools\procmon\Procmon64.exe'
$run = Join-Path $PSScriptRoot ('tests\interface-paths-' + (Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory -Path $run | Out-Null
$state = [ordered]@{run=$run; cases=@(); restored=$false; error=$null}
$ownedCapture = $false
$ownedGame = $false
$moved = $false
$config = Join-Path $system 'ScrydeGame.ini'
$original = $null
Add-Type @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class DialogLabels {
    delegate bool Callback(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h, Callback cb, IntPtr p);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    public static string[] Read(IntPtr parent) {
        var list=new List<string>();
        EnumChildWindows(parent, (h,p) => {
            var c=new StringBuilder(128); GetClassName(h,c,128);
            if(c.ToString()=="Static" || c.ToString()=="Button") {
                var s=new StringBuilder(4096); GetWindowText(h,s,4096);
                if(s.Length>0) list.Add(c.ToString()+": "+s.ToString());
            }
            return true;
        }, IntPtr.Zero);
        return list.ToArray();
    }
}
'@
try {
    if (Get-Process -Name 'Procmon*','ScrydeGame*' -ErrorAction SilentlyContinue) { throw 'Close existing game/Procmon first' }
    if ((Get-AuthenticodeSignature $procmon).Status -ne 'Valid') { throw 'Invalid Procmon signature' }
    if ((Get-FileHash "$system\Interface.u").Hash -ne '0eec3fc00817f8771663535745ebd810d873af1c1b9bf8df8b7ab126f1edc3de') { throw 'Unexpected Interface hash' }
    if (Test-Path "$test\Interface.u") { throw 'Test already contains Interface.u' }
    $original = [IO.File]::ReadAllBytes($config)
    Copy-Item $config (Join-Path $run 'ScrydeGame.ini.before')
    $text = [Text.Encoding]::UTF8.GetString($original)
    if ($text -notmatch '(?m)^Paths=\.\./Scryde/\*\.u\r?$' -or $text -match '(?m)^Paths=\.\./Test/') { throw 'Unexpected package paths' }
    foreach ($case in $Cases) {
        if ($case -eq 'relocated') {
            New-Item -ItemType Directory -Force $test | Out-Null
            Move-Item "$system\Interface.u" "$test\Interface.u"
            $moved = $true
            $modified = $text.Replace('Paths=../Scryde/*.u', "Paths=../Test/*.u`r`nPaths=../Scryde/*.u")
            [IO.File]::WriteAllBytes($config, [Text.Encoding]::UTF8.GetBytes($modified))
        }
        $pml = Join-Path $run "$case.pml"
        $csv = Join-Path $run "$case-full.csv"
        Start-Process $procmon -ArgumentList "/AcceptEula /Quiet /Minimized /NoFilter /BackingFile `"$pml`" /Runtime 100" | Out-Null
        $ownedCapture = $true
        $ready = Start-Process $procmon -ArgumentList '/WaitForIdle' -PassThru
        if (!$ready.WaitForExit(30000)) { throw 'Procmon readiness timeout' }
        $game = Start-Process "$system\ScrydeGame.exe" -WorkingDirectory $system -PassThru
        $ownedGame = $true
        Start-Sleep -Seconds 80
        $windows = @(Get-Process -Name 'ScrydeGame*' -ErrorAction SilentlyContinue | ForEach-Object {
            [pscustomobject]@{Id=$_.Id; ProcessName=$_.ProcessName; MainWindowTitle=$_.MainWindowTitle;
                labels=if($_.MainWindowHandle -ne 0){[DialogLabels]::Read($_.MainWindowHandle)}else{@()}}
        })
        Start-Process $procmon -ArgumentList '/Terminate' -Wait
        $ownedCapture = $false
        Get-Process -Name 'ScrydeGame*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction Stop
        $ownedGame = $false
        $export = Start-Process $procmon -ArgumentList "/AcceptEula /Quiet /OpenLog `"$pml`" /SaveAs `"$csv`"" -PassThru
        if (!$export.WaitForExit(120000)) { throw 'Procmon export timeout' }
        if (!(Test-Path $csv)) { throw 'Missing CSV export' }
        Import-Csv $csv | Where-Object {
            $_.'Process Name' -like 'ScrydeGame*' -and
            ($_.Path -match '(?i)(\.u$|Interface\.xdat$|\\NWindow\.dll$|\\Core\.dll$|\\Engine\.dll$|ScrydeGame(_Lite)?\.ini$)')
        } | Select-Object 'Time of Day','Process Name',PID,Operation,Path,Result |
            Export-Csv (Join-Path $run "$case-package-paths.csv") -NoTypeInformation -Encoding UTF8
        Remove-Item $csv
        $state.cases += [ordered]@{name=$case; windows=$windows; capture=$pml; events="$case-package-paths.csv"}
    }
} catch {
    $state.error = $_.Exception.Message
} finally {
    if ($ownedCapture) { Start-Process $procmon -ArgumentList '/Terminate' -Wait }
    if ($ownedGame) { Get-Process -Name 'ScrydeGame*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue }
    try {
        if ($moved) { Move-Item "$test\Interface.u" "$system\Interface.u" -ErrorAction Stop }
        if ($null -ne $original) { [IO.File]::WriteAllBytes($config, $original) }
        $state.restored = (Test-Path "$system\Interface.u") -and !(Test-Path "$test\Interface.u")
    } catch { $state.error = "$($state.error); restore: $($_.Exception.Message)" }
    $state | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $run 'result.json') -Encoding UTF8
}
if ($state.error) { exit 1 }
