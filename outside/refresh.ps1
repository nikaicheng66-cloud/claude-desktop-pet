# Copies the pieces of the desk pet that live OUTSIDE this project folder into outside\,
# so git can keep them. Run it before every commit:
#   powershell -NoProfile -ExecutionPolicy Bypass -File outside\refresh.ps1
# It only reads the originals and rewrites the copies here.
# Keep this file ASCII only: Windows PowerShell 5.1 reads a BOM-less script as ANSI.
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$project = Split-Path $here -Parent
$utf8 = New-Object System.Text.UTF8Encoding $false

# 1. Shortcuts in Startup / Desktop that point into this project
$places = @{
  startup = [Environment]::GetFolderPath('Startup')
  desktop = [Environment]::GetFolderPath('Desktop')
}
$shell = New-Object -ComObject WScript.Shell
$lines = @()
foreach ($name in ($places.Keys | Sort-Object)) {
  $dest = Join-Path $here $name
  if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
  foreach ($lnk in (Get-ChildItem $places[$name] -Filter *.lnk -ErrorAction SilentlyContinue | Sort-Object Name)) {
    $s = $shell.CreateShortcut($lnk.FullName)
    if ("$($s.TargetPath) $($s.Arguments)" -like "*$project*") {
      New-Item -ItemType Directory -Force -Path $dest | Out-Null
      Copy-Item -LiteralPath $lnk.FullName -Destination $dest
      $lines += "$name\$($lnk.Name)  ->  $($s.TargetPath) $($s.Arguments)".TrimEnd()
    }
  }
}
[System.IO.File]::WriteAllLines((Join-Path $here 'shortcuts.txt'), [string[]]$lines, $utf8)

# 2. The desk pet hooks in the user-level Claude Code settings
$settingsPath = Join-Path $env:USERPROFILE '.claude\settings.json'
$kept = [ordered]@{}
if (Test-Path $settingsPath) {
  $settings = Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($settings.PSObject.Properties['hooks']) {
    foreach ($evt in $settings.hooks.PSObject.Properties) {
      $mine = @($evt.Value | Where-Object { $_.hooks.command -match 'deskpet' })
      if ($mine.Count) { $kept[$evt.Name] = $mine }
    }
  }
}
$json = ([pscustomobject]@{ hooks = $kept }) | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText((Join-Path $here 'claude-settings-hooks.json'), $json, $utf8)

Write-Host "outside\ refreshed: $($lines.Count) shortcuts, $($kept.Count) hook events"
