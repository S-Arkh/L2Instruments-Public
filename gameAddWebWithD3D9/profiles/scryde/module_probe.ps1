param([Parameter(Mandatory=$true)][string]$System, [Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class ModuleProbe {
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct Entry {
  public uint size,id,pid,globalUsage,processUsage; public IntPtr address; public uint bytes; public IntPtr module;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string name;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string path;
 }
 public class Result { public int pid; public bool observer64=Environment.Is64BitProcess; public int snapshotError,firstError,nextError,openError,enumError; public bool toolhelpSuccess,psapiSuccess; public List<string> toolhelp=new List<string>(); public List<string> psapi=new List<string>(); public List<int> pathErrors=new List<int>(); }
 [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags,uint pid);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool Module32FirstW(IntPtr h,ref Entry e);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool Module32NextW(IntPtr h,ref Entry e);
 [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("psapi.dll",SetLastError=true)] static extern bool EnumProcessModulesEx(IntPtr h,[Out] IntPtr[] modules,uint size,out uint needed,uint filter);
 [DllImport("psapi.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern uint GetModuleFileNameExW(IntPtr h,IntPtr module,System.Text.StringBuilder path,uint size);
 public static Result Run(int pid) {
  var r=new Result();r.pid=pid;
  IntPtr snap=CreateToolhelp32Snapshot(0x18,(uint)pid);
  if(snap==new IntPtr(-1))r.snapshotError=Marshal.GetLastWin32Error();
  else {try {var e=new Entry();e.size=(uint)Marshal.SizeOf(typeof(Entry));
   if(!Module32FirstW(snap,ref e))r.firstError=Marshal.GetLastWin32Error();
   else {do {r.toolhelp.Add(e.path);} while(Module32NextW(snap,ref e));r.nextError=Marshal.GetLastWin32Error();r.toolhelpSuccess=r.toolhelp.Count>0 && r.nextError==18;}
  }finally{CloseHandle(snap);}}
  IntPtr process=OpenProcess(0x410,false,(uint)pid);
  if(process==IntPtr.Zero){r.openError=Marshal.GetLastWin32Error();return r;}
  try {var modules=new IntPtr[4096];uint needed;
   if(!EnumProcessModulesEx(process,modules,(uint)(modules.Length*IntPtr.Size),out needed,3))r.enumError=Marshal.GetLastWin32Error();
   else if(needed>modules.Length*IntPtr.Size)r.enumError=122;
   else {for(int i=0;i<needed/IntPtr.Size;i++){var p=new System.Text.StringBuilder(32768);if(GetModuleFileNameExW(process,modules[i],p,32768)==0)r.pathErrors.Add(Marshal.GetLastWin32Error());else r.psapi.Add(p.ToString());}r.psapiSuccess=r.psapi.Count>0 && r.pathErrors.Count==0;}
  }finally{CloseHandle(process);}return r;
 }
}
'@
$records=@()
# Control establishes that both enumeration methods work on this observer.
$records+=[pscustomobject]@{kind='self-control';time=(Get-Date).ToString('o');result=[ModuleProbe]::Run($PID)}
if(!(Get-Process -Name 'ScrydeGame*' -ErrorAction SilentlyContinue)) {
 $s=$System
 Start-Process "$s\ScrydeGame.exe" -WorkingDirectory $s | Out-Null
}
foreach($delay in @(20,40,40)) {
 Start-Sleep -Seconds $delay
 foreach($p in @(Get-Process -Name 'ScrydeGame*' -ErrorAction SilentlyContinue)) {
  $records+=[pscustomobject]@{kind='game';time=(Get-Date).ToString('o');title=$p.MainWindowTitle;result=[ModuleProbe]::Run($p.Id)}
 }
 $records | ConvertTo-Json -Depth 7 | Set-Content $out -Encoding UTF8
}
if(!($records | Where-Object {$_.kind -eq 'game' -and ($_.result.toolhelpSuccess -or $_.result.psapiSuccess)})){exit 2}
