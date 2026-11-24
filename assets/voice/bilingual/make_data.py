"""Generate the bilingual training set with Edge TTS (same Xiaoxiao voice as the reference audio).

Run with the Open-LLM-VTuber venv python (it has edge_tts). Output:
  wavs/*.wav (32 kHz mono) and train.list for GPT-SoVITS (path|speaker|lang|text).
"""

import asyncio
import os
import subprocess
import sys

import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from corpus import build  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FFMPEG = os.path.join(ROOT, "GPT-SoVITS-v5-20261006nvidia50x0", "runtime", "ffmpeg.exe")
WAVS = os.path.join(HERE, "wavs")
RATE, PITCH = "-12%", "+0Hz"  # same settings as ref_xiaoxiao.wav
PREFERRED = ["zh-CN-XiaoxiaoMultilingualNeural", "zh-CN-XiaoxiaoNeural"]


async def pick_voice() -> str:
    names = {v["ShortName"] for v in await edge_tts.list_voices()}
    for v in PREFERRED:
        if v in names:
            return v
    raise SystemExit("No Xiaoxiao voice available from Edge TTS")


async def one(voice, sem, rid, text):
    wav = os.path.join(WAVS, f"{rid}.wav")
    if os.path.exists(wav) and os.path.getsize(wav) > 10000:
        return True
    mp3 = os.path.join(WAVS, f"{rid}.mp3")
    async with sem:
        for attempt in range(3):
            try:
                await edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH).save(mp3)
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", mp3, "-ac", "1", "-ar", "32000", wav], check=True)
                os.remove(mp3)
                return True
            except Exception as e:
                print(f"  retry {rid}: {e}")
                await asyncio.sleep(2)
    return False


async def main():
    os.makedirs(WAVS, exist_ok=True)
    voice = await pick_voice()
    print(f"Voice: {voice}")
    rows = build()
    sem = asyncio.Semaphore(4)
    ok = await asyncio.gather(*(one(voice, sem, rid, text) for rid, _, text in rows))
    with open(os.path.join(HERE, "train.list"), "w", encoding="utf-8") as f:
        for (rid, lang, text), good in zip(rows, ok):
            if good:
                f.write(f"{os.path.join(WAVS, rid + '.wav')}|xiaoke|{lang.upper()}|{text}\n")
    print(f"Done: {sum(ok)}/{len(rows)} clips. Voice used: {voice}")
    if voice != PREFERRED[0]:
        print("NOTE: the multilingual Xiaoxiao voice was not available; used the standard one.")


asyncio.run(main())
