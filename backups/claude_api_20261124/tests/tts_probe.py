"""Where does the time of one spoken sentence go? Asks the running GPT-SoVITS server directly
(nothing is played) with the pet's own settings, and with a few variations.

Run from Open-LLM-VTuber with its venv:  python <this file> [variant ...]
"""
import io
import sys
import time
import wave

import requests
import yaml

sys.stdout.reconfigure(encoding="utf-8")
conf = yaml.safe_load(open("conf.yaml", encoding="utf-8"))["character_config"]["tts_config"]["gpt_sovits_tts"]
URL = conf["api_url"]
BASE = {
    "text_lang": conf["text_lang"], "ref_audio_path": conf["ref_audio_path"], "aux_ref_audio_paths": [],
    "prompt_lang": conf["prompt_lang"], "prompt_text": conf["prompt_text"],
    "text_split_method": conf["text_split_method"], "batch_size": int(conf["batch_size"]),
    "media_type": conf["media_type"], "streaming_mode": False, "speed_factor": float(conf["speed_factor"]),
    "temperature": float(conf["temperature"]), "top_k": int(conf["top_k"]), "top_p": float(conf["top_p"]),
    "repetition_penalty": float(conf["repetition_penalty"]), "fragment_interval": float(conf["fragment_interval"]),
    "seed": int(conf["seed"]),
}
TEXTS = ["在呢。", "好，", "好，这就把微信关掉。", "嗯，那就歇一会儿吧。",
         "看你想拿它做什么，想快点做出能用的东西就先学 Go。",
         "意思是表格里找不到名字叫 Applied 的工作表，你先看一下表格底部的标签页名字，改成一样的就行。"]
VARIANTS = {
    "as now": {},
    "cut0": {"text_split_method": "cut0"},
    "stream1": {"streaming_mode": 1},
    "stream2": {"streaming_mode": 2},
    "stream3": {"streaming_mode": 3},
    "steps8": {"sample_steps": 8},
    "steps4": {"sample_steps": 4},
    "no_parallel": {"parallel_infer": False},
}


def seconds_of(wav_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


def one(text: str, extra: dict):
    t0 = time.perf_counter()
    first = None
    data = b""
    with requests.post(URL, json=dict(BASE, text=text, **extra), stream=True, timeout=60) as r:
        if r.status_code != 200:
            return None, None, 0, f"HTTP {r.status_code}: {r.text[:120]}"
        for chunk in r.iter_content(chunk_size=4096):
            if chunk and first is None:
                first = time.perf_counter() - t0
            data += chunk
    return first, time.perf_counter() - t0, len(data), seconds_of(data)


names = sys.argv[1:] or ["as now"]
one("你好。", {})  # warm
for name in names:
    print(f"== {name} {VARIANTS[name]}")
    for text in TEXTS:
        rows = [one(text, VARIANTS[name]) for _ in range(3)]
        if rows[0][0] is None:
            print(f"   {text[:16]:18s} {rows[0][3]}")
            continue
        firsts = sorted(r[0] for r in rows)
        totals = sorted(r[1] for r in rows)
        audio = rows[0][3]
        print(f"   {len(text):3d} chars  first byte {firsts[1]:.2f}s  whole {totals[1]:.2f}s (best {totals[0]:.2f})"
              f"  audio {audio if isinstance(audio, str) else format(audio, '.1f') + 's'}  {rows[0][2] // 1024} KB   {text[:18]}")
