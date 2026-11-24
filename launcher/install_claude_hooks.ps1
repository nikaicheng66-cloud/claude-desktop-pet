# [deskpet] Adds Notification/Stop hooks to your user-level Claude Code settings so the
# desk pet can tell you when Claude Code needs you or has finished. Safe to run again.
$ErrorActionPreference = 'Stop'
$settingsPath = Join-Path $env:USERPROFILE '.claude\settings.json'
New-Item -ItemType Directory -Force -Path (Split-Path $settingsPath) | Out-Null

if (Test-Path $settingsPath) {
  Copy-Item $settingsPath "$settingsPath.bak" -Force
  $settings = Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
  $settings = [pscustomobject]@{}
}

$cmd = 'curl.exe -s -m 3 -X POST -H "Content-Type: application/json" --data-binary @- http://127.0.0.1:12393/deskpet/hook || exit 0'
$entry = @(@{ hooks = @(@{ type = 'command'; command = $cmd }) })

if (-not $settings.PSObject.Properties['hooks']) {
  $settings | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{})
}
foreach ($evt in 'Notification', 'Stop', 'UserPromptSubmit') {
  $existing = $settings.hooks.PSObject.Properties[$evt]
  if ($existing) {
    $list = @($existing.Value) | Where-Object { -not ($_.hooks.command -match 'deskpet/hook') }
    $existing.Value = @($list) + $entry
  } else {
    $settings.hooks | Add-Member -NotePropertyName $evt -NotePropertyValue $entry
  }
}

# UTF-8 without BOM (Windows PowerShell 5.1's "-Encoding UTF8" adds a BOM, which JSON readers may reject)
[System.IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding $false))
Write-Host "Done. Hooks added to $settingsPath (backup: settings.json.bak)"
