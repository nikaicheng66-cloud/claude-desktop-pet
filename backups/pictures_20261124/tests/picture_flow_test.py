"""Checks the picture feature without touching the running pet.

Run from Open-LLM-VTuber with its venv: python <this file> <scratch dir>
Real: her chat agent and persona, the local model (Ollama), the intent classifier.
Stubbed: speech, the executor (no Claude Code task may start), the intent log, screenshots.
"""
import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
scratch = Path(sys.argv[1])

from loguru import logger  # noqa: E402

logger.remove()
logger.add(sys.stderr, level="WARNING")

from src.open_llm_vtuber.agent.stateless_llm import ollama_llm  # noqa: E402

ollama_llm.OllamaLLM.cleanup = lambda self: None  # never unload the model the live pet is using

from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config  # noqa: E402
from src.open_llm_vtuber.conversations import single_conversation as sc  # noqa: E402
from src.open_llm_vtuber.conversations.tts_manager import TTSTaskManager  # noqa: E402
from src.open_llm_vtuber.deskpet import claude_bridge, pictures, router, state  # noqa: E402
from src.open_llm_vtuber.live2d_model import Live2dModel  # noqa: E402
from src.open_llm_vtuber.service_context import ServiceContext  # noqa: E402

failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    if not ok:
        failures.append(name)


def data_url(path, mime="image/jpeg"):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


NOTE = {"source": "upload", "data": data_url(scratch / "note.png", "image/png"), "mime_type": "image/png"}
CODE = {"source": "clipboard", "data": data_url(scratch / "code_1280.jpg"), "mime_type": "image/jpeg"}

# ---- stubs -------------------------------------------------------------------------------------
pictures.FOLDER = scratch / "pictures_test"
started, asked, screens, logged = [], [], [], []
claude_bridge.start = lambda request, follow_up_of=None: (started.append(request), "好，我这就去弄。")[1]


async def fake_ask(question):
    asked.append(question)


async def fake_screen(question):
    screens.append(question)


claude_bridge.ask = fake_ask
router._answer_screen = fake_screen
router._log = lambda text, label, source: logged.append((text, label, source))

spoken = []


async def fake_speak(self, tts_text, display_text, actions, live2d_model, tts_engine, websocket_send):
    spoken.append(display_text.text)


TTSTaskManager.speak = fake_speak


async def main():
    # ---- 1. the module on its own ---------------------------------------------------------------
    bad = [
        NOTE, "x", {"source": "upload"}, {"source": "weird", "data": NOTE["data"]},
        {"source": "upload", "data": "data:image/svg+xml;base64,AAAA", "mime_type": "image/svg+xml"},
        {"source": "upload", "data": "http://example.com/a.png", "mime_type": "image/png"},
        {"source": "screen", "data": "data:image/jpeg;base64,AAAA", "mime_type": "image/jpeg"},
    ]
    ok = pictures.usable(bad)
    check("usable() keeps the good picture and the screen frame, drops the rest",
          [i["source"] for i in ok] == ["upload", "screen"], str([i["source"] for i in ok]))
    check("usable() survives nonsense", pictures.usable(None) == [] and pictures.usable("abc") == [])
    check("usable() takes at most 4 given pictures", len(pictures.usable([NOTE] * 7)) == 4)
    fresh = pictures.given(pictures.usable([NOTE, CODE]))
    paths = pictures.save(fresh)
    check("save() writes both files with the right extension",
          len(paths) == 2 and paths[0].endswith(".png") and paths[1].endswith(".jpg")
          and all(Path(p).stat().st_size > 1000 for p in paths), str([Path(p).name for p in paths]))
    fake = {"source": "upload", "data": "data:image/png;base64," + base64.b64encode(b"MZ not a picture").decode(),
            "mime_type": "image/png"}
    check("save() skips a file that is not a picture", pictures.save([fake]) == [])
    check("again(): words about the picture bring it back", len(pictures.again("它上面写的什么")) == 2)
    check("again(): unrelated words do not", pictures.again("今天天气怎么样") == [])
    check("again(): words about the screen do not", pictures.again("看看我屏幕上这个") == [])
    pictures._last = (fresh, pictures.time.time() - pictures.AGAIN_SECONDS - 1)
    check("again(): not after the few minutes are over", pictures.again("它上面写的什么") == [])

    # ---- 2. the router --------------------------------------------------------------------------
    p = [str(scratch / "pictures_test" / "x.jpg")]

    async def routed(text, pics=None, about=False):
        started.clear(), asked.clear(), screens.clear(), logged.clear()
        reply = await router.route(text, pictures=pics, about_picture=about)
        await asyncio.sleep(0.05)  # let create_task'ed stubs run
        return reply

    r = await routed("看看这张图片", p, True)
    check("picture alone -> she looks herself", r is None and not started and not screens, str(logged))
    r = await routed("这是什么", p, True)
    check("'这是什么' + picture -> she looks herself", r is None and not started and not screens, str(logged))
    r = await routed("帮我看看这个报错是什么意思", p, True)
    check("'帮我看看这个报错' + picture -> she looks herself, no screenshot",
          r is None and not started and not screens, str(logged))
    r = await routed("帮我把这张图里的文字整理成一个文档", p, True)
    check("a job + picture -> executor gets the file and the 'material only' note",
          bool(r) and len(started) == 1 and p[0] in started[0] and "只是资料" in started[0], str(logged))
    check("the remembered dialogue names the file", p[0] in state.recent_dialogue(2))
    r = await routed("帮我总结一下这张图", p, True)
    check("'帮我总结一下这张图' is work -> executor", bool(r) and len(started) == 1, str(logged))
    r = await routed("图里那个人穿的什么颜色的衣服", p, True)
    check("a question about the picture -> she looks herself", r is None and not started, str(logged))
    r = await routed("这个报错怎么解决", None, True)
    check("follow-up about the picture of a moment ago -> no screenshot", not screens, str(logged))
    r = await routed("帮我把微信关了")
    check("a job without picture is unchanged", bool(r) and started == ["帮我把微信关了"], str(started))
    r = await routed("看看我屏幕上这个报错")
    check("screen question without picture still takes a screenshot",
          bool(r) and screens == ["看看我屏幕上这个报错"], str(logged))

    # ---- 3. the whole turn with her real chat agent ---------------------------------------------
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
    sent = []

    async def ws_send(text):
        sent.append(json.loads(text))

    async def turn(text, images):
        spoken.clear(), sent.clear(), started.clear(), screens.clear()
        reply = await sc.process_single_conversation(
            context=ctx, websocket_send=ws_send, client_uid="test", user_input=text, images=images)
        print(f"      你：{text}   小克：{reply}")
        return reply

    pictures.FOLDER = scratch / "pictures_test"
    state.dialogue.clear()  # the router checks above left a talk full of jobs behind
    reply = await turn("看看这张图片", [NOTE])
    check("turn: picture alone gets a spoken answer from her own model",
          bool(reply) and bool(spoken) and not started and not screens)
    check("turn: the answer is about what is in the picture",
          any(w in reply for w in ("团建", "咖啡", "通知", "pandas", "订单")), reply)
    check("turn: no error message went to the client", not [m for m in sent if m.get("type") == "error"], str(sent)[:300])
    last = ctx.agent_engine._memory[-2]
    check("turn: her memory keeps the words, not the picture",
          isinstance(last["content"], str) and "base64" not in last["content"], str(last)[:120])
    check("turn: her answer is marked as 'said about a picture' for the executor",
          "看着图片说的" in state.recent_dialogue(1))

    reply = await turn("它上面的地点写的是哪里", None)
    check("turn: a follow-up without picture still sees it", any(w in reply for w in ("湖滨", "蓝鲸", "咖啡")), reply)

    reply = await turn("帮我看看这个报错是什么意思", [CODE])
    check("turn: an error screenshot is read by her, not sent to the screen/executor path",
          bool(reply) and not started and not screens and any(w in reply for w in ("Applied", "WorksheetNotFound", "工作表", "找不到", "表")), reply)

    reply = await turn("帮我把这张图里的代码存成一个文件", [CODE])
    check("turn: a job with a picture goes to the executor with the saved file",
          len(started) == 1 and Path(re.search(r"打开看：(.+?\.jpg)", started[0]).group(1)).exists(),
          started[0][-200:] if started else "nothing started")

    # a long talk before the picture: the small context must not break the turn
    for i in range(40):
        ctx.agent_engine._memory.append({"role": "user", "content": f"第{i}件事：我今天去了超市买了苹果、牛奶和面包，还顺路取了快递。"})
        ctx.agent_engine._memory.append({"role": "assistant", "content": "[neutral] 嗯，听起来今天挺充实的。记得把牛奶放进冰箱。"})
    reply = await turn("这张图上的订单号是多少", [NOTE])
    check("turn: still works after a long conversation", bool(reply) and "A7K" in reply.upper().replace(" ", ""), reply)

    reply = await turn("今天星期几", None)
    check("turn: unrelated words afterwards go out without the picture", bool(reply), reply)

    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))


asyncio.run(main())
