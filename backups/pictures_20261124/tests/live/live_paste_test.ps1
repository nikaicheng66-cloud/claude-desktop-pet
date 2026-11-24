# Real paste on the live pet: picture to the clipboard, click her typing box, Ctrl+V, Enter.
# Keys are only sent while the pet's window is the foreground window.
param([int]$X, [int]$Y, [string]$Picture, [string]$OutDir)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
}
'@
[W]::SetProcessDPIAware() | Out-Null
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds

function ProcOf([IntPtr]$h) {
  $procId = 0
  [W]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
  try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { '' }
}
function Glide([int]$x, [int]$y) {
  $start = New-Object W+POINT
  [W]::GetCursorPos([ref]$start) | Out-Null
  for ($i = 1; $i -le 12; $i++) {
    $cx = $start.X + ($x - $start.X) * $i / 12
    $cy = $start.Y + ($y - $start.Y) * $i / 12
    [W]::mouse_event(0x8001, [uint32]($cx * 65535 / ($screen.Width - 1)), [uint32]($cy * 65535 / ($screen.Height - 1)), 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 25
  }
}
function Shot([string]$name) {
  $bmp = New-Object System.Drawing.Bitmap 520, 520
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($X - 260, $Y - 330, 0, 0, $bmp.Size)
  $bmp.Save((Join-Path $OutDir $name), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}
function PetInFront() { (ProcOf ([W]::GetForegroundWindow())) -eq 'open-llm-vtuber-electron' }

$before = New-Object W+POINT
[W]::GetCursorPos([ref]$before) | Out-Null
$front = [W]::GetForegroundWindow()
$oldText = $null; $oldImage = $null
try { if ([System.Windows.Forms.Clipboard]::ContainsText()) { $oldText = [System.Windows.Forms.Clipboard]::GetText() } } catch {}
try { if ([System.Windows.Forms.Clipboard]::ContainsImage()) { $oldImage = [System.Windows.Forms.Clipboard]::GetImage() } } catch {}

try {
  Glide $X $Y
  Start-Sleep -Milliseconds 1100
  $pt = New-Object W+POINT; $pt.X = $X; $pt.Y = $Y
  $under = ProcOf ([W]::GetAncestor([W]::WindowFromPoint($pt), 2))
  "window under the pointer: $under"
  if ($under -ne 'open-llm-vtuber-electron') { "STOP: the typing box is not under the pointer"; return }

  [W]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
  [W]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 700
  if (-not (PetInFront)) { "STOP: the pet did not take the keyboard"; return }

  $img = [System.Drawing.Image]::FromFile($Picture)
  [System.Windows.Forms.Clipboard]::SetImage($img)
  Start-Sleep -Milliseconds 300
  if (-not (PetInFront)) { "STOP: focus moved away before pasting"; return }
  [System.Windows.Forms.SendKeys]::SendWait('^v')
  Start-Sleep -Milliseconds 1800
  Shot 'paste_1_attached.png'
  "pasted"
  if (-not (PetInFront)) { "STOP: focus moved away before Enter"; return }
  [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
  Start-Sleep -Milliseconds 1500
  Shot 'paste_2_sent.png'
  "sent"
  Start-Sleep -Seconds 9
  Shot 'paste_3_answer.png'
  $img.Dispose()
}
finally {
  # give the mouse, the clipboard and the keyboard back
  Glide $before.X $before.Y
  try {
    if ($oldImage) { [System.Windows.Forms.Clipboard]::SetImage($oldImage) }
    elseif ($null -ne $oldText -and $oldText -ne '') { [System.Windows.Forms.Clipboard]::SetText($oldText) }
    else { [System.Windows.Forms.Clipboard]::Clear() }
  } catch { "clipboard not restored: $_" }
  if ($front -ne [IntPtr]::Zero) { [W]::SetForegroundWindow($front) | Out-Null }
  "mouse and clipboard given back"
}
