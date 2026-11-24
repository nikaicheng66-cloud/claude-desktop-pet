"""Where does the time to her first spoken sound go? The whole server-side turn with the real brain
(API) and the real voice (the running GPT-SoVITS server), but its own agent and a fake client:
the live pet is not touched and nothing is played.

Run from Open-LLM-VTuber with its venv:  python <this file> [rounds]
Prints, per turn, seconds since the words arrived:
  text   first piece of text from the model
  said   first sentence handed to the voice
  voice  that sentence synthesized (and how long the synthesis itself took)
  sent   first sound on its way to the client
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

for k in list(os.environ):
    if k.startswith(("ANTHROPIC_", "CLAUDE")):
        del os.environ[k]
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")

from loguru import logger  # noqa: E402

logger.remove()
logger.add(sys.stderr, level="ERROR")

from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config  # noqa: E402
from src.open_llm_vtuber.conversations import single_conversation as sc  # noqa: E402
from src.open_llm_vtuber.conversations.tts_manager import TTSTaskManager  # noqa: E402
from src.open_llm_vtuber.deskpet import claude_bridge, cloud, hub, memory, pet_llm, router, screen, state  # noqa: E402
from src.open_llm_vtuber.live2d_model import Live2dModel  # noqa: E402
from src.open_llm_vtuber.service_context import ServiceContext  # noqa: E402

memory.MEMORY_FILE = Path(tempfile.mkdtemp()) / "memory.md"


def fake_start(request, follow_up_of=None):
    """Like the real one as far as she can see it: a task that runs for a few seconds, then reports."""
    from src.open_llm_vtuber.deskpet import state as pet_state

    task = pet_state.Task(id=len(pet_state.tasks) + 1, request=request, session_id="probe")
    pet_state.tasks.append(task)

    def finish():
        task.status, task.finished, task.summary = "done", time.time(), "弄好了。"

    asyncio.get_running_loop().call_later(4, finish)
    return "好，我这就去弄。"


claude_bridge.start = fake_start
claude_bridge.cancel = lambda task: None
router._log = lambda *a: None


async def nothing(*a, **k):
    return None


claude_bridge.ask = nothing
hub.send_action = nothing
screen.screenshot = nothing

marks = {}
t0 = 0.0


def mark(name, value=None):
    marks.setdefault(name, time.perf_counter() - t0 if value is None else value)


real_cloud = pet_llm.PetClaude._cloud


async def timed_cloud(self, messages, system, turn):
    async for piece in real_cloud(self, messages, system, turn):
        mark("text")
        yield piece


pet_llm.PetClaude._cloud = timed_cloud
real_speak = TTSTaskManager.speak


async def timed_speak(self, tts_text, *a, **k):
    mark("said")
    marks.setdefault("first sentence", tts_text)
    return await real_speak(self, tts_text, *a, **k)


TTSTaskManager.speak = timed_speak


async def ws_send(text):
    msg = json.loads(text)
    if msg.get("type") == "audio" and msg.get("audio"):
        mark("sent")
        marks["sounds"] = marks.get("sounds", 0) + 1
        marks["last"] = time.perf_counter() - t0
    elif msg.get("type") == "backend-synth-complete":
        from src.open_llm_vtuber.conversations import conversation_utils

        # the client answers this when it has played everything
        asyncio.get_running_loop().call_later(
            0.01, lambda: conversation_utils.message_handler.handle_message("probe", {"type": "frontend-playback-complete"}))


ASKS = ["在吗", "今天有点累，不想干活了。", "帮我把微信关了", "你觉得我该先学 Rust 还是 Go？", "给我讲个冷笑话吧",
        "弄得怎么样了？", "刚才那个面试我感觉答得不太好。", "帮我搜一下附近的咖啡店"]


async def main():
    global t0
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    config = validate_config(read_yaml("conf.yaml"))
    ctx = ServiceContext()
    ctx.system_config = config.system_config
    ctx.character_config = config.character_config
    ctx.live2d_model = Live2dModel(config.character_config.live2d_model_name)
    ctx.history_uid = None
    ctx.translate_engine = None
    ctx.asr_engine = None
    tts_config = config.character_config.tts_config
    ctx.character_config.tts_config = None
    ctx.init_tts(tts_config)
    agent_config = config.character_config.agent_config
    ctx.character_config.agent_config = None
    await ctx.init_agent(agent_config, config.character_config.persona_prompt)

    real_generate = ctx.tts_engine.generate_audio

    def timed_generate(text, file_name_no_ext=None):
        began = time.perf_counter()
        out = real_generate(text, file_name_no_ext)
        marks.setdefault("voice", time.perf_counter() - t0)
        marks.setdefault("synthesis", time.perf_counter() - began)
        return out

    ctx.tts_engine.generate_audio = timed_generate
    await asyncio.to_thread(real_generate, "你好。")  # warm

    rows = []
    for ask in ASKS * rounds:
        marks.clear()
        t0 = time.perf_counter()
        reply = await sc.process_single_conversation(context=ctx, websocket_send=ws_send, client_uid="probe", user_input=ask)
        m = dict(marks)
        rows.append(m)
        print(f"text {m.get('text', 0):.2f}  said {m.get('said', 0):.2f}  voice {m.get('voice', 0):.2f} "
              f"(synthesis {m.get('synthesis', 0):.2f})  sent {m.get('sent', 0):.2f}  | all {m.get('sounds', 0)} sounds by {m.get('last', 0):.1f}s"
              f"  | {ask} -> {str(m.get('first sentence'))[:20]!r} / {reply[:28]!r}")
    for key in ("text", "said", "voice", "sent"):
        values = sorted(r[key] for r in rows if key in r)
        print(f"{key:6s} median {values[len(values) // 2]:.2f}s  worst {values[-1]:.2f}s")
    cloud.flush()


asyncio.run(main())
