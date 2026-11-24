"""The pet's whole server stack on a spare port (12399), with a client like live_ws_check's:
real web server, real websocket route and handler, real brain (API), real voice (the running
GPT-SoVITS server). No speech recognition, no WeChat watcher, no echo gate, no executor: the live
pet is not touched and nothing is played.

Shows, per turn, the server's own timing line and what the client measured, to see where the time
to her first sound goes between the two.

Run from Open-LLM-VTuber with its venv:  python <this file> [rounds]
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

import uvicorn  # noqa: E402
import websockets  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from loguru import logger  # noqa: E402

timing_lines = []
logger.remove()
logger.add(lambda m: timing_lines.append(m.record["message"]) if "[deskpet] turn:" in m.record["message"] or "brain:" in m.record["message"] else None, level="INFO")
logger.add(sys.stderr, level="ERROR")

from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config  # noqa: E402
from src.open_llm_vtuber.deskpet import claude_bridge, cloud, hub, memory, router, screen  # noqa: E402
from src.open_llm_vtuber.live2d_model import Live2dModel  # noqa: E402
from src.open_llm_vtuber.routes import init_client_ws_route  # noqa: E402
from src.open_llm_vtuber.service_context import ServiceContext  # noqa: E402

PORT = 12399
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
screen.screenshot = nothing

ASKS = ["在吗", "嗯", "帮我把微信关了", "今天有点累，不想干活了。", "给我讲个冷笑话吧", "你喜欢什么颜色"]


async def turn(ws, text):
    timing_lines.clear()
    t0 = time.perf_counter()
    await ws.send(json.dumps({"type": "text-input", "text": text, "images": []}))
    said, first, kinds = [], None, []
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
        kind = msg.get("type")
        kinds.append(kind if kind != "control" else f"control:{msg.get('text')}")
        if kind == "audio":
            if first is None and msg.get("audio"):
                first = time.perf_counter() - t0
            said.append((msg.get("display_text") or {}).get("text", ""))
        elif kind == "backend-synth-complete":
            await ws.send(json.dumps({"type": "frontend-playback-complete"}))
        elif kind == "control" and msg.get("text") == "conversation-chain-end":
            break
    await asyncio.sleep(0.05)
    server = next((l for l in timing_lines if "turn:" in l), "(no timing line)").replace("[deskpet] ", "")
    print(f"client: first sound {first:.2f}s, done {time.perf_counter() - t0:.2f}s | server {server} | {text} -> {''.join(said)[:24]}")
    return first


async def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    config = validate_config(read_yaml("conf.yaml"))
    ctx = ServiceContext()
    ctx.config = config
    ctx.system_config = config.system_config
    ctx.character_config = config.character_config
    ctx.live2d_model = Live2dModel(config.character_config.live2d_model_name)
    tts_config = config.character_config.tts_config
    ctx.character_config.tts_config = None
    ctx.init_tts(tts_config)
    agent_config = config.character_config.agent_config
    ctx.character_config.agent_config = None
    await ctx.init_agent(agent_config, config.character_config.persona_prompt)
    await asyncio.to_thread(ctx.tts_engine.generate_audio, "你好。")  # warm

    app = FastAPI()
    app.include_router(init_client_ws_route(default_context_cache=ctx))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    firsts = []
    try:
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/client-ws", max_size=None) as ws:
            await asyncio.sleep(1.0)  # the greeting messages
            for ask in ASKS * rounds:
                firsts.append(await turn(ws, ask))
                await asyncio.sleep(1.5)
    finally:
        server.should_exit = True
        await serving
    firsts.sort()
    print(f"first sound at the client: median {firsts[len(firsts) // 2]:.2f}s, worst {firsts[-1]:.2f}s")
    cloud.flush()


asyncio.run(main())
