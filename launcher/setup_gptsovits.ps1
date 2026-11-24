# [deskpet] One-time setup: unpack the GPT-SoVITS package from Downloads into the project.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$archive = Join-Path $env:USERPROFILE 'Downloads\GPT-SoVITS-v5-20261005nvidia50x0.7z'
$sevenZip = Join-Path $root 'Open-LLM-VTuber-Web\node_modules\7zip-bin\win\x64\7za.exe'
$target = Join-Path $root 'GPT-SoVITS'

if (Test-Path (Join-Path $target 'api_v2.py')) { Write-Host 'GPT-SoVITS is already set up.'; exit 0 }
if (-not (Test-Path $archive)) { throw "Package not found: $archive" }

Write-Host 'Unpacking GPT-SoVITS (about 10 GB, this takes a while)...'
& $sevenZip x $archive "-o$root" -y | Out-Null
if ($LASTEXITCODE -ne 0) { throw "7-Zip failed with exit code $LASTEXITCODE" }

$unpacked = Get-ChildItem $root -Directory -Filter 'GPT-SoVITS-v5-*' | Select-Object -First 1
if (-not $unpacked) { throw 'Unpacked folder not found.' }
Rename-Item $unpacked.FullName 'GPT-SoVITS'
Write-Host "Done: $target"
