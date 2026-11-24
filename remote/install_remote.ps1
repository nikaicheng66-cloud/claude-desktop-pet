# [deskpet] One-time setup for the phone remote. Right-click > Run with PowerShell.
# 1) start the remote at every login (Startup folder shortcut, no window)
# 2) allow port 12480 through Windows Firewall, but only from Tailscale addresses
# 3) start it now (unless it is already running) and print the token to type into the phone once
# Any error is shown and the window waits for Enter, so it never just flashes and closes.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "需要管理员权限（改防火墙）。马上会弹出确认框，请点「是」；接下来在新打开的窗口里继续。"
    try {
        Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    } catch {
        Write-Host "没能拿到管理员权限：$($_.Exception.Message)" -ForegroundColor Red
        Read-Host "按回车关闭"
    }
    Start-Sleep -Seconds 2
    exit
}

$ErrorActionPreference = 'Stop'
try {
    $startup = [Environment]::GetFolderPath('Startup')
    $lnk = Join-Path $startup 'deskpet-remote.lnk'
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($lnk)
    $sc.TargetPath = 'wscript.exe'
    $sc.Arguments = "`"$here\start_remote.vbs`""
    $sc.WorkingDirectory = $here
    $sc.Save()
    Write-Host "开机自启已设置：$lnk"

    Remove-NetFirewallRule -DisplayName 'deskpet remote (Tailscale only)' -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName 'deskpet remote (Tailscale only)' -Direction Inbound -Protocol TCP -LocalPort 12480 `
        -RemoteAddress 100.64.0.0/10, fd7a:115c:a1e0::/48 -Action Allow -Profile Any | Out-Null
    Write-Host "防火墙已放行 12480 端口（只允许 Tailscale 地址）"

    if (Get-NetTCPConnection -LocalPort 12480 -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "遥控服务已经在运行了"
    } else {
        Start-Process wscript.exe -ArgumentList "`"$here\start_remote.vbs`""
        Start-Sleep -Seconds 3
    }
    $token = Get-Content (Join-Path $here 'token.txt') -ErrorAction SilentlyContinue
    $tsExe = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    $ts = $null
    if (Test-Path $tsExe) { $ts = (& $tsExe ip -4 2>$null) | Select-Object -First 1 }
    Write-Host ""
    Write-Host "口令（手机上输一次）： $token"
    if ($ts) { Write-Host "手机打开：  http://${ts}:12480" } else { Write-Host "没查到 Tailscale 地址：确认 Tailscale 已登录，用 'tailscale ip -4' 查电脑的地址，手机打开 http://那个地址:12480" }
} catch {
    Write-Host ""
    Write-Host "出错了：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "（位置：第 $($_.InvocationInfo.ScriptLineNumber) 行）"
}
Read-Host "按回车关闭"
