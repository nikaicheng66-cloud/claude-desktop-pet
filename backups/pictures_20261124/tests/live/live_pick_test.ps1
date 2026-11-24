# Clicks the picture button on the live pet, checks that a file dialog opens, closes it with Esc.
param([int]$X, [int]$Y, [string]$Out)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class P {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
}
'@
[P]::SetProcessDPIAware() | Out-Null
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds

function ProcOf([IntPtr]$h) {
  $procId = 0
  [P]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
  try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { '' }
}
function ClassOf([IntPtr]$h) { $sb = New-Object System.Text.StringBuilder 256; [P]::GetClassName($h, $sb, 256) | Out-Null; $sb.ToString() }
function Glide([int]$x, [int]$y) {
  $start = New-Object P+POINT
  [P]::GetCursorPos([ref]$start) | Out-Null
  for ($i = 1; $i -le 12; $i++) {
    $cx = $start.X + ($x - $start.X) * $i / 12
    $cy = $start.Y + ($y - $start.Y) * $i / 12
    [P]::mouse_event(0x8001, [uint32]($cx * 65535 / ($screen.Width - 1)), [uint32]($cy * 65535 / ($screen.Height - 1)), 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 25
  }
}
function IsPetDialog() {
  $h = [P]::GetForegroundWindow()
  ((ClassOf $h) -eq '#32770') -and ((ProcOf $h) -eq 'open-llm-vtuber-electron')
}

$before = New-Object P+POINT
[P]::GetCursorPos([ref]$before) | Out-Null
$front = [P]::GetForegroundWindow()
try {
  Glide $X $Y
  Start-Sleep -Milliseconds 1100
  $pt = New-Object P+POINT; $pt.X = $X; $pt.Y = $Y
  $under = ProcOf ([P]::GetAncestor([P]::WindowFromPoint($pt), 2))
  "window under the pointer: $under"
  if ($under -ne 'open-llm-vtuber-electron') { "STOP: the button is not under the pointer"; return }
  [P]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
  [P]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
  $opened = $false
  for ($i = 0; $i -lt 20; $i++) { Start-Sleep -Milliseconds 250; if (IsPetDialog) { $opened = $true; break } }
  $h = [P]::GetForegroundWindow()
  "file dialog opened: $opened (foreground: $(ClassOf $h) of $(ProcOf $h))"
  if ($opened) {
    $bmp = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
    $small = New-Object System.Drawing.Bitmap $bmp, 1280, 720
    $small.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose(); $small.Dispose()
    if (IsPetDialog) { [System.Windows.Forms.SendKeys]::SendWait('{ESC}') }
    Start-Sleep -Milliseconds 800
    "file dialog closed again: " + (-not (IsPetDialog))
  }
}
finally {
  Glide $before.X $before.Y
  if ($front -ne [IntPtr]::Zero) { [P]::SetForegroundWindow($front) | Out-Null }
  "mouse given back"
}
