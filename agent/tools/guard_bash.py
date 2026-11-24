"""[deskpet] PreToolUse hook: refuse destructive shell commands in the pet's Claude Code tasks.

The --disallowedTools prefix rules (Bash(rm:*) ...) only catch a command that *starts* with
the word, so `cmd /c del`, `powershell Remove-Item` or `python -c "shutil.rmtree(...)"` slipped
through. This looks anywhere in the command. It is a safety net, not a sandbox: it stops the
common ways to delete, push, change system settings or run downloaded code.

Claude Code sends {"tool_name": ..., "tool_input": {"command": ...}} on stdin; exit code 2
blocks the call and stderr is shown to the model as the reason.
"""

import json
import re
import sys

S = r"(?:^|[\s;&|`(\"'])"  # start of a command word
RULES = [
    (S + r"rm(?:\.exe)?\s", "删除文件 (rm)"),
    (S + r"(?:rmdir|rd)\s", "删除文件夹 (rmdir/rd)"),
    (S + r"(?:del|erase)\s", "删除文件 (del)"),
    (r"remove-item|\bri\s+-r", "删除文件 (Remove-Item)"),
    (r"rmtree|os\.(?:remove|unlink|rmdir|removedirs)|\.unlink\(|\.rmdir\(|send2trash", "用脚本删除文件"),
    (r"\[io\.(?:file|directory)\]::delete|deletefile|\.delete\(\)", "用脚本删除文件"),
    (r"clear-recyclebin|cipher\s+/w", "清空回收站/擦除"),
    (S + r"format(?:\.com)?\s+[a-z]:", "格式化磁盘"),
    (S + r"(?:shutdown|restart-computer|stop-computer)\b", "关机/重启"),
    (r"\bgit\s+push\b", "git push"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\b", "git clean"),
    (r"\bgit\s+branch\s+-D\b", "删除 git 分支"),
    (r"\bgit\s+(?:checkout|restore)\s+(?:--\s+)?\.(?:\s|$)", "丢弃 git 改动"),
    (S + r"reg(?:\.exe)?\s+(?:add|delete|import|load|restore)\b", "改注册表"),
    (r"(?:set|new|remove)-itemproperty|hk(?:lm|cu|cr|u|cc):", "改注册表"),
    (r"set-mppreference|add-mppreference|netsh\s+advfirewall|bcdedit|set-executionpolicy", "改系统/安全设置"),
    (r"schtasks(?:\.exe)?\s+/(?:create|delete|change)|(?:register|unregister)-scheduledtask", "改计划任务"),
    (r"invoke-expression|\biex\b|-e(?:nc(?:odedcommand)?)?\s+[a-z0-9+/=]{20,}", "执行动态/编码过的命令"),
    (r"(?:curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm)\b[^|]*\|\s*(?:sh|bash|cmd|powershell|pwsh|python)\b",
     "下载后直接执行"),
    (r"\bnet\s+user\b|\bnet\s+localgroup\b|(?:new|remove|set)-localuser", "改系统账户"),
]
COMPILED = [(re.compile(p, re.I), why) for p, why in RULES]


def check(command: str) -> str | None:
    for rx, why in COMPILED:
        if rx.search(command or ""):
            return why
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "")
    why = check(cmd)
    if why:
        print(f"桌宠的安全规则不允许这条命令（{why}）。不要换个写法绕过；"
              "停下来，在 SAY 里告诉用户需要他自己做什么。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
