# 小克遥控（手机网页 App）

手机上看小克在干什么、打字给她下指令、远程开关她。

## 组成
- `remote_server.py`：电脑上常驻的小服务（端口 12480，只用 Python 自带库）。只接受本机和 Tailscale 地址的访问，每个请求都要口令（`token.txt`，第一次运行时自动生成）。
- `index.html` / `manifest.json` / `icon.svg`：手机上的网页 App。
- `start_remote.vbs`：无窗口启动服务。
- `install_remote.ps1`：一次性设置开机自启和防火墙。
- 小克服务端新增的接口：`/deskpet/remote/state`（状态）和 `/deskpet/remote/say`（发指令），只监听本机，由这个服务转发。

## 手机发的指令
等同于在电脑上的小克输入框里打字。它不会被"不听模式"挡住，也不会被当成说了一半的话等后半句。

## 安装
1. 电脑和手机都装 Tailscale，用同一个账号登录。
2. 右键 `install_remote.ps1` → 用 PowerShell 运行（会弹管理员确认）。它会显示口令和手机要打开的地址。
3. 重启一次小克，让新接口生效。
4. 手机打开 `http://<电脑的 Tailscale IP>:12480`，输入口令，然后"添加到主屏幕"。

## 常见问题
- 换口令：删掉 `token.txt` 后重启服务（重新登录电脑，或运行 `start_remote.vbs`）。
- 服务日志：`remote.log`。
