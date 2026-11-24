"""Regression check for the cloud brain (2026-11-24), without touching the running pet.

Run from Open-LLM-VTuber with its venv:  python <this file> [group ...]
    groups: unit flows pictures fallback   (default: all)
Real: her chat agent, persona and tools, the Anthropic API (costs a few cents), the whole turn in
single_conversation. Stubbed: speech, the executor (no Claude Code task may start), screenshots,
the intent log, her long-term memory file, the pet window.
"""
import asyncio
import base64
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

for k in list(os.environ):  # a Claude Code shell's own settings must not leak into her client
    if k.startswith(("ANTHROPIC_", "CLAUDE")):
        del os.environ[k]

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
ASSETS = Path(__file__).resolve().parents[2] / "pictures_20261124" / "tests"
scratch = Path(tempfile.mkdtemp(prefix="deskpet_brain_test_"))
flags = {a for a in sys.argv[1:] if a.startswith("--")}  # --thinking-off: the chat model never thinks first
groups = {a for a in sys.argv[1:] if not a.startswith("--")} or {"unit", "flows", "pictures", "fallback"}

from loguru import logger  # noqa: E402

logger.remove()
logger.add(sys.stderr, level="WARNING")

from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config  # noqa: E402
from src.open_llm_vtuber.conversations import single_conversation as sc  # noqa: E402
from src.open_llm_vtuber.conversations.deskpet_intent import detect_pet_commands  # noqa: E402
from src.open_llm_vtuber.conversations.tts_manager import TTSTaskManager  # noqa: E402
from src.open_llm_vtuber.deskpet import (  # noqa: E402
    brain, claude_bridge, cloud, hub, intent_llm, listening, memory, pictures, router, screen, state,
)
from src.open_llm_vtuber.live2d_model import Live2dModel  # noqa: E402
from src.open_llm_vtuber.service_context import ServiceContext  # noqa: E402

cloud.enabled = True  # as after the server has built her chat model (pet_llm.PetClaude)
failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{str(detail)[:300]}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def data_url(path, mime="image/jpeg"):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


NOTE = {"source": "upload", "data": data_url(ASSETS / "note.png", "image/png"), "mime_type": "image/png"}
CODE = {"source": "clipboard", "data": data_url(ASSETS / "code_1280.jpg"), "mime_type": "image/jpeg"}

# ---- stubs -------------------------------------------------------------------------------------
pictures.FOLDER = scratch / "pictures_test"
memory.MEMORY_FILE = scratch / "memory.md"
started, cancelled, asked, approved, logged, actions_sent, shots = [], [], [], [], [], [], []


def fake_start(request, follow_up_of=None):
    started.append((request, follow_up_of))
    return "好，我这就去弄。"


def fake_cancel(task):
    cancelled.append(task)
    task.status = "cancelled"
    task.finished = time.time()


async def fake_ask(question):
    asked.append(question)


async def fake_approve(session):
    approved.append(session)


async def fake_screenshot(for_model=False):
    shots.append(for_model)
    return str(ASSETS / "code_1280.jpg")


async def fake_send_action(cmds):
    actions_sent.append(list(cmds))


real_screenshot = screen.screenshot
claude_bridge.start = fake_start
claude_bridge.cancel = fake_cancel
claude_bridge.ask = fake_ask
router._approve = fake_approve
router._log = lambda text, label, source: logged.append((text, label, source))
screen.screenshot = fake_screenshot
screen.recent_text = lambda minutes=30: "14:01 Code.exe | sheets.py - Visual Studio Code\n14:03 chrome.exe | 哔哩哔哩"
hub.send_action = fake_send_action

spoken = []  # (seconds since the turn began, text, motions)
turn_t0 = 0.0


async def fake_speak(self, tts_text, display_text, actions, live2d_model, tts_engine, websocket_send):
    spoken.append((time.perf_counter() - turn_t0, display_text.text, list(getattr(actions, "motions", None) or [])))


TTSTaskManager.speak = fake_speak
DONE_CLAIM = re.compile(r"(已经|都)?(关(掉|上|好|闭)了|调(好|完)了|弄好了|做好了|搞定了|完成了|打开了|下(载)?好了)")
MARKUP = re.compile(r"(\*\*|^#|^- |```|[\U0001F300-\U0001FAFF])", re.M)


def reset(agent=None):
    for box in (started, cancelled, asked, approved, logged, actions_sent, shots, spoken):
        box.clear()
    state.tasks.clear(), state.sessions.clear(), state.dialogue.clear()
    state.audio_now = ""
    listening.asleep = listening.hidden = listening.vanished = False
    memory.pending = None
    pictures._last = None
    if agent is not None:
        agent._memory.clear()


def running_task(request, minutes=3, progress="", waiting=False, session="sess-1"):
    t = state.Task(id=len(state.tasks) + 1, request=request, started=time.time() - minutes * 60,
                   progress=progress, session_id=session, waiting=waiting)
    state.tasks.append(t)
    return t


def done_task(request, summary, minutes_ago=1, session="sess-0"):
    t = state.Task(id=len(state.tasks) + 1, request=request, started=time.time() - minutes_ago * 60 - 60,
                   finished=time.time() - minutes_ago * 60, status="done", summary=summary, session_id=session)
    state.tasks.append(t)
    return t


def did():
    """Labels the brain logged for the last turn."""
    return [label for _, label, source in logged if source == "brain"]


# =================================================================================================
async def unit():
    print("\n== unit ==")
    k = cloud.key()
    check("the key is found in the DeskPet variable", bool(k) and k.startswith("sk-ant-"))
    check("the client always talks to api.anthropic.com", str(cloud.client().base_url).startswith("https://api.anthropic.com"))
    config = validate_config(read_yaml("conf.yaml"))
    c = config.character_config.agent_config.llm_configs.claude_llm
    check("conf.yaml is valid: Claude chat, key not in the file, qwen as backup",
          config.character_config.agent_config.agent_settings.basic_memory_agent.llm_provider == "claude_llm"
          and c.llm_api_key == "" and c.api_key_env == "DeskPet" and c.model == "claude-sonnet-5-5"
          and c.fallback_model == "qwen3.5:2b", c)
    check("no key in conf.yaml or the logs' config dump", "sk-ant" not in json.dumps(config.model_dump(), default=str))

    import anthropic
    import httpx

    def err(cls, status, message="x"):
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        return cls(message, response=httpx.Response(status, request=req), body=None)

    check("an expired key is explained as such", "key" in cloud.explain(err(anthropic.AuthenticationError, 401)).why)
    check("no credit is explained as such",
          "余额" in cloud.explain(err(anthropic.BadRequestError, 400, "Your credit balance is too low")).why)
    check("a dead network is explained as such",
          "网络" in cloud.explain(anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))).why)

    from src.open_llm_vtuber.agent.stateless_llm.claude_llm import AsyncLLM, KEEP_MESSAGES, TRIM_STEP

    llm = AsyncLLM(llm_api_key="test")
    talk = []
    for i in range(150):
        talk += [{"role": "user", "content": f"u{i}", "name": "Human"}, {"role": "assistant", "content": f"a{i}"}]
    talk.append({"role": "user", "content": [{"type": "text", "text": "now"}]})
    sizes = set()
    firsts = []
    for n in range(1, len(talk) + 1, 2):
        msgs = llm._prepare(talk[:n])
        sizes.add(len(msgs))
        firsts.append(msgs[0]["content"] if isinstance(msgs[0]["content"], str) else msgs[0]["content"][0]["text"])
        assert msgs[0]["role"] == "user" and "name" not in msgs[0]
    check("a long talk is cut to a window", max(sizes) <= KEEP_MESSAGES + TRIM_STEP, max(sizes))
    changes = sum(1 for a, b in zip(firsts, firsts[1:]) if a != b)
    check("the window moves in steps, so the cached beginning holds", changes <= len(talk) // TRIM_STEP + 1, changes)
    msgs = llm._prepare(talk)
    check("the cache mark sits just before the newest message",
          msgs[-2]["content"][-1].get("cache_control") == {"type": "ephemeral"} and "cache_control" not in msgs[-1]["content"][-1])
    check("an empty talk is survived", llm._prepare([]) == [] and llm._prepare([{"role": "assistant", "content": "x"}]) == [])

    reset()
    note = brain.state_note(None)
    check("note: nothing running", "没有在做的事" in note, note)
    running_task("帮我投那几家高匹配的岗位", 4, "刚写好 Acme 的求职信。", waiting=True)
    done = brain.state_note(brain.Turn("好了吗", moved=["walk:left"]))
    check("note: the running task, its progress, the page waiting for him, the move already done",
          all(w in done for w in ("帮我投那几家", "Acme", "等用户自己动手", "walk:left")), done)
    reset()
    done_task("装一下 VLC", "官网的 VLC 是 3.0.21，要我装吗？", 2)
    note = brain.state_note(None)
    check("note: the last task and that it ended on a question", "VLC" in note and "在问他" in note, note)
    state.sessions["s"] = state.Session("s", r"C:\x\ai-job-search", "自动投递", message="Claude needs your permission to use Bash", waiting=True)
    listening.asleep = True
    note = brain.state_note(None)
    check("note: a window waiting for approval, and not-listening mode", "等他确认" in note and "不听模式" in note, note)
    check("the tool list is fixed and every tool has a handler",
          {t["name"] for t in brain.TOOLS} == set(brain._RUN) and len(brain.TOOLS) == 8)

    from src.open_llm_vtuber.deskpet import timing

    new_system = "新的人设……直接接他的话。\n## 表情\n- [joy], [wave]\n" + brain._MOVE_LINE_NOW + "\n- [walk_left]\n\n## 用户让你记住的事\n- 喝咖啡不加糖"
    local = brain.local_system(new_system)
    check("local model: the old persona and rules, the same tags and memory after them",
          local.startswith("你叫 Claude，大家也叫你小克。你是住在用户电脑桌面上的桌宠助手")
          and "先用一个很短的句子回应" in local and "【不能撒谎】" in local and "直接接他的话" not in local
          and "[walk_left]" in local and "喝咖啡不加糖" in local
          and brain._MOVE_LINE_OLD in local and brain._MOVE_LINE_NOW not in local, local[-200:])

    reset()

    async def slow_lookup():
        await asyncio.sleep(0.2)

    job = asyncio.create_task(brain._tracked("alas 现在跑得怎么样", slow_lookup()))
    await asyncio.sleep(0.05)
    during = brain.state_note(None)
    await job
    check("note: a look-up under way is in her view until it has reported",
          "你正在查：alas 现在跑得怎么样" in during and "正在查" not in brain.state_note(None), during)

    timing.begin()
    timing.mark("heard")
    timing.mark("said")
    timing.mark("said")
    timing.mark("voice", synthesis=0.6)
    got = timing.marks()
    check("turn timing: first time of each step only", list(got) == ["heard", "said", "voice"] and got["heard"] <= got["said"] <= got["voice"], got)
    timing.report()
    check("turn timing: gone after the report", timing.marks() == {})

    # --- her voice: the first, quick piece of a reply, and the order of synthesis
    from src.open_llm_vtuber.utils.sentence_divider import SentenceDivider

    async def pieces(reply):
        divider = SentenceDivider(faster_first_response=True, segment_method="pysbd", valid_tags=["think"])

        async def stream():
            for i in range(0, len(reply), 2):
                yield reply[i:i + 2]

        return [x.text async for x in divider.process_stream(stream())]

    cases = {
        "[joy] 好，我这就去把微信关掉。": "[joy] 好，",
        "[neutral] 在呀。有什么事，说吧。": "[neutral] 在呀。",
        "[sadness] 才早上八点多就累了呀……昨晚是不是没睡好？": "[sadness] 才早上八点多就累了呀……",
        "[thinking] 嗯……我想想，先学 Go 吧。": "[thinking] 嗯……",
        "[neutral] 好的、没问题，我这就去。": "[neutral] 好的、",
    }
    got = {reply: await pieces(reply) for reply in cases}
    check("voice: the first piece ends at the earliest comma or finished ellipsis",
          all(got[r][0] == first for r, first in cases.items()), {r: g[0] for r, g in got.items()})
    check("voice: nothing of the reply is lost or doubled by the cut",
          all("".join(g).replace(" ", "") == r.replace(" ", "") for r, g in got.items()), got)

    from src.open_llm_vtuber.tts.gpt_sovits_tts import TTSEngine

    engine = TTSEngine()
    served, busy, overlap = [], [0], [False]

    def fake_synthesis(text, file_name_no_ext=None):
        busy[0] += 1
        overlap[0] = overlap[0] or busy[0] > 1
        time.sleep(0.12 if text == "一" else 0.02)  # the first sentence is the slowest one
        served.append(text)
        busy[0] -= 1
        return text

    engine.generate_audio = fake_synthesis
    await asyncio.gather(*(asyncio.create_task(engine.async_generate_audio(t)) for t in "一二三四"))
    check("voice: sentences are synthesized one at a time, in the order spoken", served == list("一二三四") and not overlap[0], served)

    check("asleep: a short sentence may be a call", listening.maybe_calling("喂在吗"))
    check("asleep: a long sentence with her name may be a call",
          listening.maybe_calling("这个季度的指标我们再看一下然后还有几个事情要对一下另外小克你出来一下帮我看看这个东西怎么弄的啊我现在有点搞不明白了"))
    check("asleep: a long meeting sentence is not sent anywhere",
          not listening.maybe_calling("这个季度的指标我们再看一下然后还有几个事情要对一下包括上个月的营收和成本结构以及下个季度的招聘计划和预算安排这些都需要讨论"))

    reset()
    brain.begin("帮我调到25", [])
    turn = brain.take()
    check("a turn is handed out once", turn is not None and brain.take() is None)
    check("job text: his words first, her reading as a hint",
          brain._job(turn, "把系统音量调到 25").startswith("帮我调到25（小克对这句话的理解") and brain._job(turn, "帮我调到25。") == "帮我调到25")
    brain.finish(brain.Turn("躲一下"), "[smirk] 好，我去角落。[walk_bottom_right][hide_right]")
    check("her own tags are followed on the server side", listening.hidden and not listening.vanished)
    brain.finish(brain.Turn("隐身吧"), "好。[vanish]")
    check("... vanish too", listening.vanished)

    shot = await real_screenshot(for_model=True)  # the real thing once (kept on this PC, sent nowhere here)
    from PIL import Image

    size = Image.open(shot).size if shot else None
    check("a real screenshot for her model: a JPEG no wider than 1920",
          bool(shot) and shot.endswith(".jpg") and max(size) <= 1920 and brain._picture_block(shot) is not None, (shot, size))

    from src.open_llm_vtuber.deskpet import quiet

    writing, overlapped, sent_order = [0], [False], []

    async def slow_socket(data):  # a socket that is still busy with the last (big) message
        writing[0] += 1
        overlapped[0] = overlapped[0] or writing[0] > 1
        await asyncio.sleep(0.03)
        sent_order.append(json.loads(data)["n"])
        writing[0] -= 1

    gate = quiet.Gate(slow_socket)
    await asyncio.gather(*(gate.send_text(json.dumps({"type": "x", "n": n})) for n in range(6)))
    check("writes to one client go out one at a time, in order", not overlapped[0] and sent_order == list(range(6)), sent_order)

    reset()
    answer = await intent_llm.is_wake("小克你出来吧")
    check("small model (cloud): 'come out' is a call", answer is True)
    answer = await intent_llm.is_wake("这个季度的指标我们再看一下")
    check("small model (cloud): meeting talk is not", answer is False)
    line = await intent_llm.one_line("I finished tailoring the CV and cover letter for Acme and submitted the application on Workday. Tracker updated.")
    check("small model (cloud): one spoken line in Chinese", bool(line) and len(line) <= 60 and re.search(r"[\u4e00-\u9fff]", line) and "Acme" in line, line)
    cmds = await intent_llm.pick_moves("去右上角躲着")
    check("small model (cloud): body commands", cmds == ["walk:top_right", "hide:right"], cmds)


# =================================================================================================
async def make_context():
    config = validate_config(read_yaml("conf.yaml"))
    ctx = ServiceContext()
    ctx.system_config = config.system_config
    ctx.character_config = config.character_config
    ctx.live2d_model = Live2dModel(config.character_config.live2d_model_name)
    ctx.history_uid = None
    ctx.translate_engine = None
    ctx.tts_engine = None
    ctx.asr_engine = None
    agent_config = config.character_config.agent_config
    ctx.character_config.agent_config = None  # so init_agent builds it
    await ctx.init_agent(agent_config, config.character_config.persona_prompt)
    if "--thinking-off" in flags:
        ctx.agent_engine._llm.thinking = {"thinking": {"type": "between_tools"}}
        print("      (thinking switched off for this run)")
    return ctx


sent = []
first_words = []


async def ws_send(text):
    sent.append(json.loads(text))


async def say(ctx, text, images=None, quiet=False):
    """One whole user turn, as typed into her box (text) - the same path a spoken sentence takes after recognition."""
    global turn_t0
    for box in (started, cancelled, asked, approved, logged, actions_sent, shots, spoken, sent):
        box.clear()
    turn_t0 = time.perf_counter()
    reply = await sc.process_single_conversation(
        context=ctx, websocket_send=ws_send, client_uid="test", user_input=text, images=images)
    took = time.perf_counter() - turn_t0
    await asyncio.sleep(0.05)  # let create_task'ed stubs run
    first = spoken[0][0] if spoken else took
    first_words.append(first)
    if not quiet:
        print(f"      你：{text}\n      小克（{first:.1f}s 开口，共 {took:.1f}s）：{reply}")
    return reply


def errors():
    return [m for m in sent if m.get("type") == "error"]


async def flows(ctx):
    print("\n== whole turns, cloud brain ==")
    agent = ctx.agent_engine
    check("she runs on the pet's Claude class with qwen as backup",
          type(agent._llm).__name__ == "PetClaude" and agent._llm.model == "claude-sonnet-5-5"
          and agent._llm.fallback_model == "qwen3.5:2b" and agent._llm.effort == "low")

    # --- plain talk
    reset(agent)
    r = await say(ctx, "今天有点累，不想干活了。")
    check("chat: an answer, nothing started, no error", bool(r) and not started and not errors() and did() == ["CHAT"], (started, errors(), did()))
    check("chat: spoken style (no markdown, emoji, lists)", not MARKUP.search(r), r)
    r2 = await say(ctx, "你觉得我该先学 Rust 还是 Go？")
    check("chat: gives an opinion", bool(r2) and ("Rust" in r2 or "Go" in r2) and not started, r2)
    check("chat: the talk is remembered for later jobs", "Rust" in state.recent_dialogue(2))
    r = await say(ctx, "我刚才问你先学哪个来着？")
    check("chat: she remembers the conversation", "Rust" in r or "Go" in r, r)

    # --- comments that contain action words are not jobs
    for text in ("你刚才为什么要打开它", "我都吐槽一句啊，你要干什么？", "你打开东西是对的", "下载这种事以后还是我自己来比较放心吧"):
        reset(agent)
        r = await say(ctx, text)
        check(f"comment, not a job: {text}", not started and not cancelled, started)

    # --- a job
    reset(agent)
    r = await say(ctx, "帮我把微信关了")
    check("job: handed over once, in his own words", len(started) == 1 and started[0][0].startswith("帮我把微信关了") and started[0][1] is None, started)
    check("job: she says something first, and does not claim it is done", bool(r) and not DONE_CLAIM.search(r), r)
    check("job: logged as TASK by the brain", did() == ["TASK"], logged)
    check("job: no second model round for a fire-and-forget tool", len(spoken) >= 1)

    for text in ("声音太大了", "播放音乐", "把屏幕亮度调低一点", "帮我看看刚才找出来的岗位，哪些匹配度高", "搜一下最近有什么数据分析的实习"):
        reset(agent)
        r = await say(ctx, text, quiet=True)
        check(f"job: {text}", len(started) == 1 and not DONE_CLAIM.search(r or ""), (started, r))

    # --- follow-up that only makes sense with the talk before it
    reset(agent)
    await say(ctx, "帮我下个东西", quiet=True)
    first_started = list(started)
    r = await say(ctx, "VLC 播放器")
    all_started = first_started + started
    check("job across two sentences: the executor is told what 'it' is",
          any("VLC" in s[0] for s in all_started) and len(all_started) <= 2, all_started)

    # --- while something is running
    reset(agent)
    cur = running_task("帮我投那几家高匹配的岗位", 6, "刚写好 Acme 的求职信和简历。")
    r = await say(ctx, "弄得怎么样了？")
    check("status: answered from what is really going on, nothing started", not started and not cancelled and ("Acme" in r or "求职信" in r or "投" in r), r)
    check("status: does not claim it is finished", not re.search(r"(都投完了|已经投完|全部搞定)", r), r)
    r = await say(ctx, "顺便把 Massive 那个也投了")
    check("while running: a new request still goes to the queue logic", len(started) == 1 and "Massive" in started[0][0], started)
    r = await say(ctx, "只投 fit 是 high 的，其他先不要投")
    check("while running: a constraint is passed on", len(started) == 1 and not cancelled, (started, cancelled))
    r = await say(ctx, "算了算了，别弄了")
    check("cancel: the running task is stopped", cancelled == [cur] and not started, (cancelled, started))
    check("cancel: logged", "CANCEL" in did(), logged)

    reset(agent)
    cur = running_task("帮我投 Acme 的那个岗位", 5, "表格填到一半。")
    r = await say(ctx, "先别提交，先把简历里的项目顺序重排一下再投")
    check("hold with a new way: stopped, and continued in the same session with the new request",
          cancelled == [cur] and len(started) == 1 and started[0][1] is cur and "重排" in started[0][0], (cancelled, started))
    reset(agent)
    cur = running_task("帮我投 Acme 的那个岗位", 5, "表格填到一半。")
    r = await say(ctx, "先别提交，等我看看")
    check("hold: stopped, nothing new started", cancelled == [cur] and not started, (cancelled, started))

    reset(agent)
    cur = running_task("帮我投 Management Solutions", 8, waiting=True)
    r = await say(ctx, "我登好了")
    check("'done on my side' while she waits on a page: passed on, not cancelled", not cancelled and len(started) <= 1, (cancelled, started))

    # --- she asked something, he answers
    reset(agent)
    last = done_task("帮我装个 VLC", "官网最新的 VLC 是 3.0.21，要我现在装吗？", 1)
    r = await say(ctx, "装吧")
    check("answer to her question: the same session goes on", len(started) == 1 and started[0][1] is last, started)
    reset(agent)
    last = done_task("帮我装个 VLC", "官网最新的 VLC 是 3.0.21，要我现在装吗？", 1)
    r = await say(ctx, "VLC 是哪个公司做的来着？")
    check("a question back is not taken as a yes", not started, started)

    # --- answers that only make sense with what she reported before (the old router sent these on blindly)
    reset(agent)
    last = done_task("帮我投 Acme 那个岗位", "Acme 的表格里问你最早什么时候能入职，你告诉我我接着填。", 2)
    agent._memory.append({"role": "assistant", "content": last.summary})  # as hub.say(..., remember=True) leaves it
    r = await say(ctx, "下个月一号就能入职")
    check("answering what she asked in her report: passed on to the same session",
          len(started) == 1 and started[0][1] is last and "一号" in started[0][0], started)
    reset(agent)
    last = done_task("帮我投那几家高匹配的", "你要的五家里投好了三家，还有两家等你：Massive 要你登录，Acme 的条款页有三个勾选项，要我都选同意吗？", 3)
    agent._memory.append({"role": "assistant", "content": last.summary})
    r = await say(ctx, "都选同意")
    check("'都选同意' after her question: continues that job", len(started) == 1 and started[0][1] is last, started)
    reset(agent)
    cur = running_task("帮我投 Management Solutions 和 Best Buy", 9, "Management Solutions 的表格填到一半。", waiting=True)
    agent._memory.append({"role": "assistant", "content": "Management Solutions 那页要邮箱验证码，还问你打没打过高尔夫、有没有写作样本。"})
    r = await say(ctx, "验证码你帮我填进去就行，高尔夫打过室内的，写作样本没有")
    check("answers while she waits on a page: passed on, the job is not stopped",
          len(started) == 1 and not cancelled and "高尔夫" in started[0][0], (started, cancelled))
    reset(agent)
    agent._memory.append({"role": "assistant", "content": "我找到二十二个新岗位，其中十八个是高匹配的，清单我打开给你了。要投吗？"})
    done_task("搜一下今天的新岗位", "我找到二十二个新岗位，其中十八个是高匹配的，清单我打开给你了。要投吗？", 4)
    r = await say(ctx, "这18家都投吧，简历和 cover letter 你直接都生成好")
    check("'这18家都投吧' after her report: a job, no questions back", len(started) == 1 and "18" in started[0][0], (started, r))
    reset(agent)
    r = await say(ctx, "帮我把本地的和那几个最匹配的都投一下吧", quiet=True)
    check("a clear job with things she can't place: handed over, not questioned", len(started) == 1, (started, r))
    reset(agent)
    r = await say(ctx, "今天投了几家？", quiet=True)
    check("counting needs the real records: a job for the executor, not a guess", len(started) == 1 and not asked, (started, asked, r))
    for text in ("帮我看一下现在电脑的系统音量是多少", "现在开着哪些程序？"):
        reset(agent)
        r = await say(ctx, text, quiet=True)
        check(f"the PC's state right now needs a command, so it is a job: {text}", len(started) == 1 and not asked, (started, asked, r))
    reset(agent)
    r = await say(ctx, "alas 现在跑得怎么样", quiet=True)
    check("'how is that program doing': looked up read-only", len(asked) == 1 and not started, (asked, started, r))
    reset(agent)
    for text in ("你去睡吧", "小克接着睡", "闭嘴，安静一会儿"):
        listening.asleep = False
        r = await say(ctx, text, quiet=True)
        check(f"sleep words: {text}", listening.asleep, r)
    reset(agent)
    r = await say(ctx, "我要去睡觉了，晚安", quiet=True)
    check("he goes to bed himself: just good night", not started, r)
    reset(agent)
    r = await say(ctx, "谢谢你呀", quiet=True)
    check("thanks is not a job (the old router once made it one)", not started and not asked, r)

    # --- approval
    reset(agent)
    state.sessions["s"] = state.Session("s", r"C:\x\ai-job-search", "自动投递",
                                        message="Claude needs your permission to use Bash", waiting=True)
    r = await say(ctx, "可以，帮我点一下")
    check("approve: goes to look at the waiting window", len(approved) == 1 and not started, (approved, started))
    reset(agent)
    r = await say(ctx, "可以")
    check("no window waiting: '可以' approves nothing", not approved and not started, (approved, started))

    # --- not listening
    reset(agent)
    r = await say(ctx, "我要开会了，你先别听我说话")
    check("sleep: she stops listening and tells the pet window", listening.asleep and actions_sent and actions_sent[0][0] == "sleep", (listening.asleep, actions_sent))
    check("sleep: she says how to call her back", "名字" in r or "叫我" in r, r)
    gate = await router.listen_gate("这个季度的指标我们再看一下")
    check("asleep: meeting talk is ignored silently", gate == "" and listening.asleep)
    gate = await router.listen_gate("小克")
    check("asleep: her name brings her back", bool(gate) and not listening.asleep, gate)
    reset(agent)
    r = await say(ctx, "帮我让电脑休眠")
    check("'put the PC to sleep' is a job, not 'stop listening'", not listening.asleep and len(started) == 1, (listening.asleep, started))
    reset(agent)
    listening.asleep = True
    gate = await router.listen_gate("小克，帮我查一下明天的天气，然后继续睡")
    check("asleep + named + 'stay asleep': handled, still asleep", gate is None and listening.asleep)
    r = await say(ctx, "小克，帮我查一下明天的天气，然后继续睡")
    check("... the job is done and she stays in not-listening mode", len(started) == 1 and listening.asleep, (started, listening.asleep))

    # --- long-term memory
    reset(agent)
    r = await say(ctx, "记住，我喝咖啡不加糖")
    check("remember: saved at once", any("咖啡" in e for e in memory.items()), memory.items())
    r = await say(ctx, "你都记得我什么？")
    check("recall: she tells it from memory", "咖啡" in r or "糖" in r, r)
    r = await say(ctx, "以后早上别跟我说早安了")
    saved_already = any("早安" in e for e in memory.items())
    r2 = await say(ctx, "好，记下吧")
    check("a passing 'from now on': asked first, saved after the yes",
          any("早安" in e for e in memory.items()) and (saved_already or "?" in r or "？" in r or "吗" in r), (r, memory.items()))
    r = await say(ctx, "咖啡那条忘掉吧")
    check("forget: the entry is gone", not any("咖啡" in e for e in memory.items()), memory.items())

    # --- the screen
    reset(agent)
    r = await say(ctx, "看看我屏幕上这个报错是什么意思")
    check("screen: she takes a (small) screenshot herself and answers from it",
          shots == [True] and not started and any(w in r for w in ("Applied", "WorksheetNotFound", "工作表", "找不到", "表")), (shots, r))
    reset(agent)
    r = await say(ctx, "我刚才在干嘛来着")
    check("screen: 'what was I doing' uses the window timeline", shots == [True] and any(w in r for w in ("哔哩", "B站", "b站", "sheets", "代码", "视频", "Code")), r)

    # --- her body
    reset(agent)
    text = "去左边待着"
    check("(the rule catches this move)", detect_pet_commands(text) == ["walk:left"])
    r = await say(ctx, text)
    moves = [m for m in sent if m.get("type") == "pet-action"]
    tags = [m for s in spoken for m in s[2]]
    check("move by rule: done once, she only agrees", moves and moves[0]["motions"] == ["walk:left"] and not [t for t in tags if t.startswith(("walk", "hide", "nudge"))], (moves, tags))
    reset(agent)
    text = "你这样我看不到右下角的进度条了"
    check("(no rule catches this one)", detect_pet_commands(text) == [])
    r = await say(ctx, text)
    tags = [m for s in spoken for m in s[2]]
    check("move by understanding: she moves out of the way with her own tag", any(t.startswith(("walk", "hide", "nudge")) or t == "vanish" for t in tags), (tags, r))

    # --- health
    reset(agent)
    r = await say(ctx, "你现在能操作电脑吗？")
    check("health: answered from the facts, nothing started", bool(r) and not started and "不" not in r[:6], r)

    # --- a long talk before
    reset(agent)
    for i in range(120):
        agent._memory.append({"role": "user", "content": f"第{i}件事：我今天去了超市买了苹果、牛奶和面包，还顺路取了快递。"})
        agent._memory.append({"role": "assistant", "content": "[neutral] 嗯，听起来今天挺充实的。记得把牛奶放进冰箱。"})
    r = await say(ctx, "帮我把记事本打开")
    check("after a very long talk: still works", len(started) == 1 and not errors(), (started, errors()))

    # --- nothing she is not asked for
    reset(agent)
    meta = {"proactive_speak": True, "skip_memory": True, "skip_history": True}
    for box in (started, spoken, sent):
        box.clear()
    reply = await sc.process_single_conversation(context=ctx, websocket_send=ws_send, client_uid="test",
                                                 user_input="Please say something that would be engaging and appropriate for the current context.",
                                                 images=None, metadata=meta)
    check("speaking up on her own: a line, no job", bool(reply) and not started and not errors(), (reply, started))
    print(f"      （主动说话）小克：{reply}")


async def picture_flows(ctx):
    print("\n== pictures ==")
    agent = ctx.agent_engine
    reset(agent)
    r = await say(ctx, "看看这张图片", [NOTE])
    check("picture alone: she looks herself and says what is in it",
          bool(r) and not started and not shots and any(w in r for w in ("团建", "咖啡", "通知", "pandas", "订单")), r)
    last = agent._memory[-2]
    check("her memory keeps the words, not the picture", isinstance(last["content"], str) and "base64" not in last["content"])
    check("her answer is marked as 'said about a picture' for the executor", "看着图片说的" in state.recent_dialogue(1))
    r = await say(ctx, "它上面的地点写的是哪里")
    check("a follow-up without the picture still sees it", any(w in r for w in ("湖滨", "蓝鲸", "咖啡")), r)
    reset(agent)
    r = await say(ctx, "帮我看看这个报错是什么意思", [CODE])
    check("an error screenshot given as a picture: read by her, no screenshot, no job",
          bool(r) and not started and not shots and any(w in r for w in ("Applied", "WorksheetNotFound", "工作表", "找不到", "表")), (r, started, shots))
    r = await say(ctx, "帮我把这张图里的代码存成一个文件", [CODE])
    ok = len(started) == 1 and re.search(r"打开看：(.+?\.jpg)", started[0][0]) and "只是资料" in started[0][0]
    check("a job with a picture: the executor gets the saved file and the 'material only' note",
          bool(ok) and Path(re.search(r"打开看：(.+?\.jpg)", started[0][0]).group(1)).exists(), started)
    reset(agent)
    r = await say(ctx, "这张图上的订单号是多少", [NOTE])
    check("reading a detail off a picture", "A7K" in (r or "").upper().replace(" ", ""), r)


async def fallback(ctx):
    print("\n== cloud unreachable: the local backup ==")
    agent = ctx.agent_engine
    llm = agent._llm
    from anthropic import AsyncAnthropic

    real_client, real_shared = llm.client, cloud._client
    reset(agent)
    # 0. a request that hangs before its first event (seen on about one in twenty): a second one is sent
    real_begin, calls = llm._begin, []

    async def hanging_first(**request):
        calls.append(time.perf_counter())
        if len(calls) == 1:
            await asyncio.sleep(9)
        return await real_begin(**request)

    llm._begin = hanging_first
    r = await say(ctx, "你好呀")
    check("a hanging request: asked a second time after 2 s, answered once, still on Claude",
          bool(r) and len(calls) == 2 and spoken and spoken[0][0] < 5.5 and did() == ["CHAT"] and cloud.usable(),
          (len(calls), spoken[:1], logged))
    llm._begin = real_begin
    await asyncio.sleep(0.3)
    reset(agent)
    # 1. a wrong key (as after it expired)
    llm.client = cloud._client = AsyncAnthropic(api_key="sk-ant-api03-expired", base_url=cloud.BASE_URL, max_retries=0, timeout=20)
    told = []
    local_llm = llm._local_llm()
    real_local = local_llm.chat_completion

    def spying_local(messages, system=None, tools=None):
        told.append(system or "")
        return real_local(messages, system) if tools is None else real_local(messages, system, tools)

    local_llm.chat_completion = spying_local
    r = await say(ctx, "今天有点累，不想干活了。")
    check("expired key: she still answers (local model), and says once what is wrong",
          bool(r) and "key" in r and "本地" in r and not errors(), (r, errors()))
    check("the outage sentence is spoken, not only shown (no brackets)", not r.lstrip().startswith(("（", "(")), r[:30])
    check("local model: it is given the old persona and rules, not the new guidance",
          bool(told) and "先用一个很短的句子回应" in told[0] and "【不能撒谎】" in told[0]
          and "直接接他的话" not in told[0] and "你的手" not in told[0] and "## 表情" in told[0], told[0][:120] if told else "nothing")
    check("expired key: the cloud is left alone for a while", not cloud.usable())
    r = await say(ctx, "帮我把微信关了")
    check("local path: a job is still handed over (old rules)", len(started) == 1 and started[0][0] == "帮我把微信关了", started)
    check("local path: the outage is not announced a second time", "key" not in (r or ""), r)
    r = await say(ctx, "那你觉得周末去哪玩比较好？")
    check("local path: plain talk still gets an answer", bool(r) and not started and not errors(), (r, errors()))
    gate = await router.listen_gate("先别听我说话了，我要开会")
    check("local path: the 'stop listening' rule works again", bool(gate) and listening.asleep, gate)
    listening.asleep = False
    answer = await intent_llm.is_wake("Claude")  # (the 2B model gets few of these right; the rules come first)
    moves = await intent_llm.pick_moves("去右上角躲着")
    check("local path: the small questions fall back to the local model too",
          answer is True and moves == ["walk:top_right", "hide:right"], (answer, moves))

    # 2. no network at all
    cloud.worked()
    llm.client = cloud._client = AsyncAnthropic(api_key=cloud.key(), base_url="http://127.0.0.1:9", max_retries=0, timeout=5)
    reset(agent)
    t0 = time.perf_counter()
    r = await say(ctx, "你好呀")
    check("no network: answered locally, the reason is said", bool(r) and "网络" in r and not errors(), (r, errors()))
    check("no network: found out quickly", time.perf_counter() - t0 < 25, time.perf_counter() - t0)

    # 3. back again
    llm.client, cloud._client = real_client, real_shared
    cloud.worked()
    reset(agent)
    r = await say(ctx, "你好呀")
    check("cloud back: she is on Claude again", bool(r) and cloud.usable() and did() == ["CHAT"], (r, logged))

    # 3b. qwen chosen as the chat model in conf.yaml (llm_provider: 'ollama_llm'): everything the old way
    cloud.enabled = False
    reset(agent)
    system_then = agent._system_now()
    check("local chat model chosen: the old persona", "先用一个很短的句子回应" in system_then and "直接接他的话" not in system_then, system_then[:80])
    check("local chat model chosen: nothing is asked of the cloud", not cloud.usable() and await cloud.small("x", [], "y") is None)
    quick = await router.route("帮我把微信关了")
    check("local chat model chosen: the old rules decide and answer", bool(quick) and len(started) == 1 and started[0][0] == "帮我把微信关了" and "云端" not in quick, (quick, started))
    gate = await router.listen_gate("先别听我说话了，我要开会")
    check("local chat model chosen: the 'stop listening' rule", bool(gate) and listening.asleep, gate)
    listening.asleep = False
    cloud.enabled = True
    reset(agent)

    # 4. the monthly budget
    real_budget = cloud.MONTHLY_BUDGET_USD
    cloud.MONTHLY_BUDGET_USD = 0.0
    check("budget used up: the cloud is not asked any more", not cloud.usable() and "额度" in cloud._down_why)
    cloud.MONTHLY_BUDGET_USD = real_budget
    cloud.worked()

    import httpx

    async with httpx.AsyncClient(timeout=5) as c:
        ps = (await c.get("http://127.0.0.1:11434/api/ps")).json()
    until = [(m["name"], m.get("expires_at", "")[:19]) for m in ps.get("models", [])]
    print(f"      Ollama now: {until}")
    check("the backup model is no longer kept loaded for ever",
          all(not e.startswith(("0001", "2318", "2317", "2300")) and e[:4] <= str(time.localtime().tm_year + 1) for _, e in until), until)


async def main():
    if "unit" in groups:
        await unit()
    if groups & {"flows", "pictures", "fallback"}:
        ctx = await make_context()
        if "flows" in groups:
            await flows(ctx)
        if "pictures" in groups:
            await picture_flows(ctx)
        if "fallback" in groups:
            await fallback(ctx)
        if first_words:
            ordered = sorted(first_words)
            print(f"\n      first word: median {ordered[len(ordered) // 2]:.2f}s, slowest {ordered[-1]:.2f}s over {len(ordered)} turns")
    print(f"      spent this month so far: ${cloud.spent_this_month():.3f}")
    cloud.flush()
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED:\n  " + "\n  ".join(failures)))


asyncio.run(main())
