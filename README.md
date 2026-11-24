# 小克：住在 Windows 桌面上的 AI 桌宠

小克是一只 Live2D 桌宠，待在桌面一角。你可以用语音或打字跟她聊天，也可以让她替你操作电脑：调音量、开关程序、找文件、在网页上填表。聊天由 Claude 负责，动电脑的活交给 Claude Code 在后台完成，做完她会用自己的声音告诉你结果。

她基于开源项目 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) 改造而成，一共分三个仓库：

| 仓库 | 内容 |
|---|---|
| [Open-LLM-VTuber](https://github.com/nikaicheng66-cloud/Open-LLM-VTuber)（fork） | 服务端：对话、语音识别和合成，加上新增的 `deskpet` 模块 |
| [Open-LLM-VTuber-Web](https://github.com/nikaicheng66-cloud/Open-LLM-VTuber-Web)（fork） | Electron 客户端：透明的桌宠窗口和聊天气泡 |
| **本仓库** | 启动器、执行端、微信联动、手机遥控、测试 |

## 她能做什么

- **聊天**：用 Claude API（Sonnet 负责对话和调用工具，Haiku 处理简短判断）。每句话由模型自己判断是闲聊、要做事、问进度，还是叫停；行为主要靠一段指导文字和人设来塑造，不靠关键词规则。连不上网时自动退回本地 Ollama 小模型和关键词规则。
- **替你动电脑**：需要动手的请求，会交给 Claude Code（`claude -p`）在 `agent/` 目录里执行。她先应一声，做的过程中报进度，做完用一两句话说结果。中途可以补充、改主意或叫停。删除、推送、付款、发消息这类操作会被安全钩子拦下来，停下来问你。
- **语音**：Faster-Whisper 识别语音，GPT-SoVITS 用训练好的音色合成，按句依次合成，第一句话大约 1.6–1.9 秒出声。回声门会过滤麦克风录到的电脑自身声音，所以她不会把自己的话当成你说的。
- **看图和看屏幕**：可以把图片粘贴、拖到她身上或从文件选择。问屏幕上有什么时，她现截一张图来看。
- **音频拖放**：把录音拖到她身上，她会转成文字并写出摘要。
- **不听模式**：说一声「先别听」，她就安静待着，直到你叫她的名字。
- **长期记忆**：让她记住的事存在 `agent/memory.md`，可以直接打开改。
- **Claude Code 提醒**：其他 Claude Code 窗口要权限或做完任务时，她会告诉你（通过 `launcher/install_claude_hooks.ps1` 装的钩子）。
- **微信联动**（`wechat_auto/`）：人不在电脑前时听到微信消息提示音，就把系统音量调到 0；可选的自动回复只针对一位指定联系人，默认关闭。
- **手机遥控**（`remote/`）：手机网页 App，通过 Tailscale 访问，可以看她在做什么、打字给她下指令。

## 怎么工作

```
麦克风 / 打字 / 手机
        │
        ▼
 Open-LLM-VTuber 服务端 ── deskpet/brain.py：Claude 决定怎么回、要不要调用工具
        │                        │
        │                        └─ do_on_computer ─► claude_bridge.py ─► Claude Code（agent/ 目录）
        ▼
 GPT-SoVITS 合成语音 ─► Electron 桌宠窗口：Live2D 表情和动作、聊天气泡
```

服务端的主要模块都在 `Open-LLM-VTuber/src/open_llm_vtuber/deskpet/`：

- `brain.py`、`pet_llm.py`、`cloud.py`：云端大脑，含预算和本地备用。
- `router.py`：本地备用时用的规则。
- `claude_bridge.py`：把任务交给 Claude Code。
- `echo_gate.py`：回声门。
- `pictures.py`：看图。
- `audio_drop.py`：处理拖进来的录音。
- `timing.py`：记录每一轮时间花在了哪里。

## 运行环境

- Windows 11，NVIDIA 显卡（GPT-SoVITS 要用）
- Python 和 [uv](https://github.com/astral-sh/uv)、Node.js
- [Ollama](https://ollama.com)，用于本地备用模型
- [Claude Code](https://claude.com/claude-code)，已登录
- Anthropic API 密钥，放在用户环境变量 `DeskPet` 里（不写进任何文件）
- 可选：Tailscale（手机遥控）、Chrome 和 Claude in Chrome（网页操作）

## 搭起来

1. 把三个仓库放进同一个文件夹，目录结构如下：

   ```
   claude-desktop-pet/          ← 本仓库
     Open-LLM-VTuber/           ← 服务端 fork
     Open-LLM-VTuber-Web/       ← 客户端 fork
     GPT-SoVITS-v5-…/           ← GPT-SoVITS 整合包（需自行下载）
   ```

   ```bash
   git clone https://github.com/nikaicheng66-cloud/claude-desktop-pet.git
   ```

   ```bash
   cd claude-desktop-pet && git clone https://github.com/nikaicheng66-cloud/Open-LLM-VTuber.git && git clone https://github.com/nikaicheng66-cloud/Open-LLM-VTuber-Web.git
   ```

2. 服务端：在 `Open-LLM-VTuber` 里运行 `uv sync`，然后按需修改 `conf.yaml`。
3. 客户端：在 `Open-LLM-VTuber-Web` 里依次运行 `npm install`、`npm run build`、`npx electron-builder --dir`。
4. 语音：
   - 准备 GPT-SoVITS 整合包和你自己的参考音频，放到 `assets/voice/`。
   - 训练语料在 `assets/voice/bilingual/`，用 `launcher/make_voice_data.bat` 和 `launcher/train_voice.bat` 训练。
   - 推理配置在 `launcher/gsv_tts_infer.yaml`。
5. 设置 API 密钥：在 PowerShell 里运行 `[Environment]::SetEnvironmentVariable('DeskPet', '<你的密钥>', 'User')`。
6. 启动：双击 `launcher/start_deskpet.vbs`。它会依次检查 Ollama、启动语音服务和服务端，再以桌宠模式打开客户端；关掉客户端时，它启动的服务也会一起停掉。
7. 可选：
   - `launcher/install_claude_hooks.ps1`：接入 Claude Code 提醒。
   - `remote/install_remote.ps1`：设置手机遥控，详见 [remote/README.md](remote/README.md)。

## 测试

回归测试在 `backups/*/tests/`，用服务端的 `.venv/Scripts/python.exe` 运行，不影响正在运行的桌宠：

- `brain_flow_test.py`：整轮对话测试，执行端是替身，不会真的动电脑。
- `picture_flow_test.py`：看图流程。
- `stack_probe.py`：在备用端口上测语音延迟。

## 不在仓库里的

- 声音素材和训练好的音色权重
- 立绘源文件
- 运行日志、聊天记录、截图、手机口令（`remote/token.txt`）
- 微信联系人识别数据

## 许可证

- 服务端沿用上游的 MIT 许可证。
- 客户端沿用上游的 Open-LLM-VTuber License 1.0：个人、非商业使用免费，商用需另取授权。
- Live2D Cubism SDK 和示例模型按 Live2D 的条款使用。
