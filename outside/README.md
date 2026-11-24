# Xiaoke's files outside this folder

This folder keeps copies of things that belong to Xiaoke but live outside the `claude-desktop-pet` folder, so git can store them.

Run `refresh.ps1` before every commit. It only reads the originals and rewrites the copies here; the originals are never changed.

```
powershell -NoProfile -ExecutionPolicy Bypass -File outside\refresh.ps1
```

| File here | Where the original is | How to restore it |
|---|---|---|
| `startup\DeskPet.lnk` | the Startup folder (Win+R, `shell:startup`) | copy it back |
| `startup\deskpet-remote.lnk` | the same | copy it back, or run `remote\install_remote.ps1` |
| `desktop\*.lnk` | the desktop | copy it back |
| `shortcuts.txt` | — | a record of where each shortcut points |
| `claude-settings-hooks.json` | the `hooks` in `%USERPROFILE%\.claude\settings.json` | run `launcher\install_claude_hooks.ps1` |

The shortcut copies and `shortcuts.txt` hold local paths, so they are created on your own PC and not published.

Never stored here or in git: the user environment variable `DeskPet` (the API key) and `remote\token.txt` (the phone token).
