"""Replay what the user really said to her (agent/intent_log.jsonl) through the new brain and
compare what she does with what the old router did.

Run from Open-LLM-VTuber with its venv:  python <this file> [max sentences]
Each sentence is asked on its own (no talk before it, nothing running), so sentences that only
made sense as a follow-up are expected to differ: the differences are printed to be read, not
counted as failures. Nothing is started: the executor and the pet window are stubbed.
"""
import asyncio
import collections
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
from src.open_llm_vtuber.deskpet import brain, claude_bridge, cloud, hub, intent_llm, memory, router, screen, state  # noqa: E402
from src.open_llm_vtuber.live2d_model import Live2dModel  # noqa: E402
from src.open_llm_vtuber.service_context import ServiceContext  # noqa: E402

LOG = Path(os.getcwd()).parent / "agent" / "intent_log.jsonl"
limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 400
memory.MEMORY_FILE = Path(tempfile.mkdtemp()) / "memory.md"

did = collections.defaultdict(list)  # per task: what was called


def note(name):
    did[asyncio.current_task()].append(name)


claude_bridge.start = lambda request, follow_up_of=None: (note("TASK"), "好，我这就去弄。")[1]
claude_bridge.cancel = lambda task: note("CANCEL")


async def fake_ask(q):
    pass


async def fake_shot(for_model=False):
    return None


async def nothing(*a, **k):
    pass


claude_bridge.ask = fake_ask
screen.screenshot = fake_shot
router._approve = nothing
router._log = lambda *a: None
router._go_to_sleep = nothing
hub.send_action = nothing

# what counts as "the same" as the old label
SAME = {
    "TASK": {"TASK"},
    "CHAT": {"CHAT", "MOVE", "MEMORY"},
    "STATUS": {"STATUS", "CHAT"},  # with nothing running the old answer was a fixed "nothing is running"
    "SCREEN": {"SCREEN"},
    "SLEEP": {"SLEEP"},
    "CANCEL": {"CANCEL", "CHAT"},  # nothing is running in the replay, so there is nothing to stop
}


async def main():
    seen, cases = set(), []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        text, label, by = d.get("text", ""), d.get("label"), d.get("by", "")
        if label not in SAME or by in ("brain", "audio") or text in seen or len(text) < 2 or text.startswith("<"):
            continue
        seen.add(text)
        cases.append((text, label, by))
    # the hand-written examples of the old classifier are the best-labelled set there is
    for q, a in intent_llm._EXAMPLES:
        if "最后一句" not in q and a in SAME and q not in seen:
            seen.add(q)
            cases.append((q, a, "example"))
    cases = cases[-limit:]
    if "diff" in sys.argv:  # only what differed from the old router in the first round
        first = Path(__file__).with_name("intent_replay_round1.jsonl")
        cases = [(r["text"], r["old"], r["by"]) for r in map(json.loads, first.read_text(encoding="utf-8").splitlines())
                 if r["new"] not in SAME[r["old"]]]
    print(f"{len(cases)} sentences")

    config = validate_config(read_yaml("conf.yaml"))
    ctx = ServiceContext()
    ctx.system_config = config.system_config
    ctx.character_config = config.character_config
    ctx.live2d_model = Live2dModel(config.character_config.live2d_model_name)
    system = await ctx.construct_system_prompt(config.character_config.persona_prompt)
    c = config.character_config.agent_config.llm_configs.claude_llm
    from src.open_llm_vtuber.deskpet.pet_llm import PetClaude

    llm = PetClaude(model=c.model, base_url=c.base_url, llm_api_key=c.llm_api_key, effort=c.effort,
                    max_tokens=c.max_tokens, api_key_env=c.api_key_env)
    gate = asyncio.Semaphore(6)
    rows = []

    async def one(text, label, by):
        async with gate:
            turn = brain.Turn(text)
            reply, t0, first = "", time.perf_counter(), None
            try:
                async for piece in llm._cloud([{"role": "user", "content": text}], system, turn):
                    first = first or time.perf_counter() - t0
                    reply += piece
            except Exception as e:
                reply = f"<error {e}>"
            got = (turn.did or did.get(asyncio.current_task()) or
                   (["MOVE"] if brain._TAG.search(reply) else ["CHAT"]))[0]
            rows.append((text, label, by, got, reply.replace("\n", " "), first or 0))

    await asyncio.gather(*(one(*c) for c in cases))
    same = [r for r in rows if r[3] in SAME[r[1]]]
    diff = [r for r in rows if r[3] not in SAME[r[1]]]
    firsts = sorted(r[5] for r in rows if r[5])
    print(f"same as before: {len(same)} / {len(rows)}   first word median {firsts[len(firsts) // 2]:.2f}s, 90% under {firsts[int(len(firsts) * 0.9)]:.2f}s")
    print(collections.Counter((r[1], r[3]) for r in diff).most_common())
    print("\n--- different from the old router (old -> new) ---")
    for text, label, by, got, reply, _ in sorted(diff, key=lambda r: (r[1], r[3])):
        print(f"[{label} -> {got}] ({by}) {text}\n        小克：{reply[:150]}")
    out = Path(__file__).with_name("intent_replay_diff.jsonl" if "diff" in sys.argv else "intent_replay_result.jsonl")
    out.write_text("\n".join(json.dumps(dict(text=r[0], old=r[1], by=r[2], new=r[3], reply=r[4]), ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"\nall rows: {out}\nspent this month so far: ${cloud.spent_this_month():.3f}")
    cloud.flush()


asyncio.run(main())
