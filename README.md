# Xiaoke: an AI desk pet that lives on your Windows desktop

Xiaoke (小克) is a Live2D desk pet that sits in a corner of your screen. You can chat with her by voice or by typing, and you can ask her to work the computer for you: change the volume, open or close programs, find files, fill in forms on web pages. Claude does the talking; jobs on the computer go to Claude Code in the background, and when a job is done she tells you the result in her own voice.

She is built on the open-source project [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) and spread over three repositories:

| Repository | What it holds |
|---|---|
| [Open-LLM-VTuber](https://github.com/nikaicheng66-cloud/Open-LLM-VTuber) (fork) | Server: conversation, speech recognition and synthesis, plus the new `deskpet` module |
| [Open-LLM-VTuber-Web](https://github.com/nikaicheng66-cloud/Open-LLM-VTuber-Web) (fork) | Electron client: the transparent pet window and the chat bubble |
| **this repository** | Launcher, task executor, WeChat link, phone remote, tests |

She speaks and understands Chinese; English words inside Chinese sentences are fine.

## What she can do

- **Chat**: through the Claude API (Sonnet for the conversation and tool calls, Haiku for short judgements). The model itself decides what each sentence is for: small talk, a job, a progress question, or "stop". Her behaviour is shaped by a guidance text and her persona, not by keyword rules. Without a connection she falls back to a small local model in Ollama and keyword rules.
- **Work the computer**: requests that need action go to Claude Code (`claude -p`), which runs in the `agent/` folder. She acknowledges first, reports progress along the way, and sums up the result in a sentence or two. You can add details, change your mind or stop her halfway. Deleting, pushing, paying and sending messages are blocked by a safety hook, and she stops to ask you instead.
- **Voice**: Faster-Whisper recognises speech; GPT-SoVITS speaks with a trained voice, one sentence after another, so the first words come about 1.6 to 1.9 seconds after she starts answering. An echo gate drops what the microphone picks up from the PC's own speakers, so she never takes her own words for yours.
- **Pictures and the screen**: paste a picture, drop it on her, or pick a file. Ask what is on the screen and she takes a fresh screenshot to look at.
- **Audio drop**: drop a recording on her and she transcribes it and writes a summary.
- **Not-listening mode**: tell her to stop listening and she stays quiet until you call her name.
- **Long-term memory**: things you ask her to remember are kept in `agent/memory.md`, a plain file you can edit.
- **Claude Code notifications**: when another Claude Code window needs permission or finishes, she tells you (hooks installed by `launcher/install_claude_hooks.ps1`).
- **WeChat link** (`wechat_auto/`): when a WeChat message sound plays while you are away from the PC, the system volume goes to 0. An optional auto-reply answers one chosen contact only and is off by default.
- **Phone remote** (`remote/`): a web app for your phone, reached over Tailscale, to see what she is doing and type instructions to her.

## How it works

```
microphone / typing / phone
        │
        ▼
 Open-LLM-VTuber server ── deskpet/brain.py: Claude decides how to answer and whether to call a tool
        │                        │
        │                        └─ do_on_computer ─► claude_bridge.py ─► Claude Code (agent/ folder)
        ▼
 GPT-SoVITS voice ─► Electron pet window: Live2D expressions and motions, chat bubble
```

The main server modules are in `Open-LLM-VTuber/src/open_llm_vtuber/deskpet/`:

- `brain.py`, `pet_llm.py`, `cloud.py`: the cloud brain, with a budget and the local backup.
- `router.py`: the rules used on the local backup path.
- `claude_bridge.py`: hands jobs to Claude Code.
- `echo_gate.py`: the echo gate.
- `pictures.py`: pictures.
- `audio_drop.py`: dropped recordings.
- `timing.py`: logs where each turn's time went.

## Requirements

- Windows 11 and an NVIDIA graphics card (for GPT-SoVITS)
- Python with [uv](https://github.com/astral-sh/uv), and Node.js
- [Ollama](https://ollama.com) for the local backup model
- [Claude Code](https://claude.com/claude-code), signed in
- An Anthropic API key in the user environment variable `DeskPet` (never written to a file)
- Optional: Tailscale (phone remote), Chrome with Claude in Chrome (web pages)

## Setting it up

1. Put the three repositories into one folder, laid out like this:

   ```
   claude-desktop-pet/          ← this repository
     Open-LLM-VTuber/           ← server fork
     Open-LLM-VTuber-Web/       ← client fork
     GPT-SoVITS-v5-…/           ← GPT-SoVITS package (download it yourself)
   ```

   ```bash
   git clone https://github.com/nikaicheng66-cloud/claude-desktop-pet.git
   ```

   ```bash
   cd claude-desktop-pet && git clone https://github.com/nikaicheng66-cloud/Open-LLM-VTuber.git && git clone https://github.com/nikaicheng66-cloud/Open-LLM-VTuber-Web.git
   ```

2. Server: run `uv sync` in `Open-LLM-VTuber`, then adjust `conf.yaml` as needed.
3. Client: in `Open-LLM-VTuber-Web`, run `npm install`, `npm run build` and `npx electron-builder --dir`.
4. Voice:
   - Get the GPT-SoVITS package and your own reference audio, and put the audio in `assets/voice/`.
   - The training sentences are in `assets/voice/bilingual/`; train with `launcher/make_voice_data.bat` and `launcher/train_voice.bat`.
   - The inference settings are in `launcher/gsv_tts_infer.yaml`.
5. API key: in PowerShell, run `[Environment]::SetEnvironmentVariable('DeskPet', '<your key>', 'User')`.
6. Start: double-click `launcher/start_deskpet.vbs`. It checks Ollama, starts the voice server and the main server, then opens the client in pet mode. Closing the client also stops the servers it started.
7. Optional:
   - `launcher/install_claude_hooks.ps1`: Claude Code notifications.
   - `remote/install_remote.ps1`: the phone remote, see [remote/README.md](remote/README.md).

## Tests

Regression tests are in `backups/*/tests/`. Run them with the server's `.venv/Scripts/python.exe`; they leave a running pet alone:

- `brain_flow_test.py`: whole conversation turns, with a stand-in executor that never touches the PC.
- `picture_flow_test.py`: the picture flow.
- `stack_probe.py`: measures voice latency on a spare port.

## Not in the repository

- Voice recordings and trained voice weights
- The character art source files
- Logs, chat history, screenshots, the phone token (`remote/token.txt`)
- The data used to recognise a WeChat contact

## Licences

- Server: MIT, as upstream.
- Client: Open-LLM-VTuber License 1.0, as upstream. Free for personal and non-commercial use; commercial use needs a separate licence.
- The Live2D Cubism SDK and sample models are used under Live2D's terms.
