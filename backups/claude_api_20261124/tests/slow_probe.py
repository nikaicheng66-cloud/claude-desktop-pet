"""Why is a turn sometimes slow? Times each request of the brain, with what the model spent.

Run from Open-LLM-VTuber with its venv:  python <this file> [effort]
"""
import asyncio
import logging
import os
import sys
import time

for k in list(os.environ):
    if k.startswith(("ANTHROPIC_", "CLAUDE")):
        del os.environ[k]
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.INFO)  # shows "Retrying request ..."

from loguru import logger  # noqa: E402

logger.remove()

from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config  # noqa: E402
from src.open_llm_vtuber.deskpet import brain, cloud  # noqa: E402
from src.open_llm_vtuber.live2d_model import Live2dModel  # noqa: E402
from src.open_llm_vtuber.service_context import ServiceContext  # noqa: E402

ASKS = ["可以", "你都记得我什么？", "先别提交，先把简历里的项目顺序重排一下再投", "以后早上别跟我说早安了",
        "小克，帮我查一下明天的天气，然后继续睡", "今天有点累", "帮我把微信关了", "你觉得周末去哪玩好", "弄得怎么样了？",
        "这个报错怎么办啊，烦死了", "你喜欢什么颜色", "帮我搜一下附近的咖啡店"]


async def main():
    effort = sys.argv[1] if len(sys.argv) > 1 else "low"
    extra = {}
    if len(sys.argv) > 2 and sys.argv[2] == "between_tools":
        extra["thinking"] = {"type": "between_tools"}
    config = validate_config(read_yaml("conf.yaml"))
    ctx = ServiceContext()
    ctx.system_config = config.system_config
    ctx.character_config = config.character_config
    ctx.live2d_model = Live2dModel(config.character_config.live2d_model_name)
    system = await ctx.construct_system_prompt(config.character_config.persona_prompt) + brain.GUIDE
    client = cloud.client()

    raw = await client.messages.with_raw_response.create(
        model=cloud.CHAT_MODEL, max_tokens=16, messages=[{"role": "user", "content": "hi"}],
        output_config={"effort": "low"})
    print({k: v for k, v in raw.headers.items() if "ratelimit" in k and ("limit" in k.split("ratelimit-")[1] or "remaining" in k)})

    rows = []
    asks = ASKS * 2 if len(sys.argv) < 4 else [a for a in sys.argv[3].split("|")] * int(sys.argv[4] if len(sys.argv) > 4 else 4)
    for ask in asks:
        msgs = [{"role": "user", "content": ask}, {"role": "system", "content": brain.state_note(brain.Turn(ask))}]
        t0 = time.perf_counter()
        first_event = first_text = None
        kinds = []
        async with client.messages.stream(
            model=cloud.CHAT_MODEL, max_tokens=4000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=msgs, tools=brain.TOOLS, output_config={"effort": effort}, **extra,
        ) as stream:
            async for ev in stream:
                first_event = first_event or time.perf_counter() - t0
                if ev.type == "content_block_start":
                    kinds.append(ev.content_block.type)
                if ev.type == "content_block_delta" and ev.delta.type == "text_delta" and first_text is None:
                    first_text = time.perf_counter() - t0
            final = await stream.get_final_message()
        total = time.perf_counter() - t0
        u = final.usage
        rows.append(first_text or total)
        print(f"{ask[:14]:16s} first event {first_event:5.2f}s  first text {(first_text or 0):5.2f}s  total {total:5.2f}s  "
              f"out={u.output_tokens:4d} cache_read={u.cache_read_input_tokens} in={u.input_tokens}  blocks={kinds}")
    rows.sort()
    print(f"effort {effort} {extra}: first text median {rows[len(rows) // 2]:.2f}s, worst {rows[-1]:.2f}s")


asyncio.run(main())
