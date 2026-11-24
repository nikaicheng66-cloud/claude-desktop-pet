# 目录外的小克文件

这里存的是不在 `claude-desktop-pet` 文件夹里、但属于小克的东西的副本，让它们能随 git 一起保存。

每次提交前运行一次 `refresh.ps1`：它只读取原件，重新生成这里的副本，不改动原件。

```
powershell -NoProfile -ExecutionPolicy Bypass -File outside\refresh.ps1
```

| 这里的文件 | 原件在哪 | 怎么恢复 |
|---|---|---|
| `startup\DeskPet.lnk` | 开机启动文件夹（Win+R 输入 `shell:startup`） | 复制回去 |
| `startup\deskpet-remote.lnk` | 同上 | 复制回去，或运行 `remote\install_remote.ps1` 重建 |
| `desktop\*.lnk` | 桌面 | 复制回去 |
| `shortcuts.txt` | — | 只是记录每个快捷方式指向哪里 |
| `claude-settings-hooks.json` | `%USERPROFILE%\.claude\settings.json` 里的 `hooks` | 运行 `launcher\install_claude_hooks.ps1` 重新写入 |

不在这里、也永远不进 git：用户环境变量 `DeskPet`（API 密钥）、`remote\token.txt`（手机端口令）。
