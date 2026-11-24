"""[deskpet] WeChat auto-reply, part 6: the summary in 小克's own voice, as an audio file.

Uses the pet's local GPT-SoVITS server with the voice settings from conf.yaml, so it sounds like
her. No cloud fallback: the summary of someone's shared video stays on this PC, and a different
voice would not be "her" anyway. Plays nothing and sends nothing.
"""

import io
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import requests
import yaml

from video import CannotReply

SERVER = Path(__file__).resolve().parent.parent / "Open-LLM-VTuber"
MAX_SECONDS = 59.0  # WeChat voice messages stop at 60 s
MIN_SECONDS = 1.0
TIMEOUT = 300       # nobody is waiting; a busy GPU took 108 s for 19 s of speech


def settings() -> dict:
    conf = yaml.safe_load((SERVER / "conf.yaml").read_text(encoding="utf-8"))
    return dict(conf["character_config"]["tts_config"]["gpt_sovits_tts"])


def speakable(text: str) -> str:
    """The same clean-up her normal speech gets (English words, symbols)."""
    src = str(SERVER / "src")
    if src not in sys.path:
        sys.path.append(src)
    from open_llm_vtuber.deskpet import speech

    return speech.normalize(text)


def synthesize(text: str) -> bytes:
    """WAV bytes of her saying `text`, short enough for one voice message."""
    body = settings()
    url = body.pop("api_url")
    body["batch_size"] = int(body.get("batch_size", 1))
    body["streaming_mode"] = False
    body["media_type"] = "wav"
    body["text"] = speakable(text)
    try:
        r = requests.post(url, json=body, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise CannotReply(f"her voice server is not answering: {e}") from e
    if r.status_code != 200:
        raise CannotReply(f"her voice server failed: HTTP {r.status_code}")
    length = seconds(r.content)
    if not MIN_SECONDS <= length <= MAX_SECONDS:
        raise CannotReply(f"the spoken summary is {length:.0f}s long")
    return r.content


def seconds(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


def save_mp3(wav: bytes, path: Path) -> Path:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise CannotReply("ffmpeg not found")
    p = subprocess.run([exe, "-y", "-loglevel", "error", "-i", "pipe:0", "-b:a", "96k", str(path)], input=wav,
                       capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode:
        raise CannotReply(f"could not make the mp3: {p.stderr.decode('utf-8', 'replace')[-200:]}")
    return path
