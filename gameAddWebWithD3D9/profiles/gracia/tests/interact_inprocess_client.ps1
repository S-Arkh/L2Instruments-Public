param([int]$ProcessId,[int]$X=-1,[int]$Y=-1,[string]$Screenshot='screen.png',[int]$WaitSeconds=5)
$ErrorActionPreference='Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class BrowserTestInput {
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int x,y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int left,top,right,bottom; }
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref Point p);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out Rect p);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc callback, IntPtr p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
    public static IntPtr GameWindow(uint wanted) {
        IntPtr found=IntPtr.Zero;
        EnumWindows((h,p)=>{uint pid; GetWindowThreadProcessId(h,out pid); var title=new System.Text.StringBuilder(256);GetWindowText(h,title,256);
            if(pid==wanted && title.ToString()=="Lineage II"){found=h;return false;}return true;},IntPtr.Zero);
        return found;
    }
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint d,UIntPtr e);
}
'@
$p=Get-Process -Id $ProcessId
if($p.Path -notlike '*\tests\inprocess-client-*\system\L2.exe'){throw 'Only isolated test clients are allowed'}
$window=[BrowserTestInput]::GameWindow($ProcessId)
if($window -eq [IntPtr]::Zero){throw 'Game window not found'}
if($X -ge 0 -and $Y -ge 0) {
    [BrowserTestInput]::SetForegroundWindow($window) | Out-Null
    Start-Sleep -Milliseconds 300
    if([BrowserTestInput]::GetForegroundWindow() -ne $window){throw 'Test client is not foreground'}
    $point=New-Object BrowserTestInput+Point;$point.x=$X;$point.y=$Y
    [BrowserTestInput]::ClientToScreen($window,[ref]$point) | Out-Null
    [BrowserTestInput]::SetCursorPos($point.x,$point.y) | Out-Null
    Start-Sleep -Milliseconds 200
    [BrowserTestInput]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
    Start-Sleep -Milliseconds 100
    [BrowserTestInput]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
}
Start-Sleep -Seconds $WaitSeconds
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if([BrowserTestInput]::GetForegroundWindow() -ne $window){Write-Host 'Screenshot skipped: client lost foreground';return}
$rect=New-Object BrowserTestInput+Rect
[BrowserTestInput]::GetWindowRect($window,[ref]$rect) | Out-Null
$bounds=New-Object Drawing.Rectangle($rect.left,$rect.top,($rect.right-$rect.left),($rect.bottom-$rect.top))
$image=New-Object Drawing.Bitmap($bounds.Width,$bounds.Height)
$graphics=[Drawing.Graphics]::FromImage($image)
$graphics.CopyFromScreen($bounds.Location,[Drawing.Point]::Empty,$bounds.Size)
$image.Save((Join-Path (Split-Path (Split-Path $p.Path)) $Screenshot))
$graphics.Dispose();$image.Dispose()
