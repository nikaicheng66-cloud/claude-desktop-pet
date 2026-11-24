# Saves a region of the screen (physical pixels) as PNG.
param([int]$X, [int]$Y, [int]$W, [int]$H, [string]$Out)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public class DpiB { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }
'@
[DpiB]::SetProcessDPIAware() | Out-Null
$bmp = New-Object System.Drawing.Bitmap $W, $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($X, $Y, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"saved"
