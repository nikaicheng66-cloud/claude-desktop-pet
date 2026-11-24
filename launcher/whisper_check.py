"""[deskpet] Download the Whisper model once and check whether it runs on the graphics card."""
import os, sys
from pathlib import Path
import numpy as np

# same DLL lookup as the server: CUDA libraries from the nvidia-* pip packages
for base in map(Path, sys.path):
    for bin_dir in (base / "nvidia").glob("*/bin") if (base / "nvidia").is_dir() else []:
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
from faster_whisper import WhisperModel

silence = np.zeros(16000, dtype=np.float32)
try:
    m = WhisperModel("large-v3-turbo", download_root="models/whisper", device="cuda", compute_type="int8_float16")
    list(m.transcribe(silence)[0])
    print("RESULT: GPU OK")
except Exception as e:
    print("RESULT: GPU NOT USABLE ->", e)
    m = WhisperModel("large-v3-turbo", download_root="models/whisper", device="cpu", compute_type="int8")
    list(m.transcribe(silence)[0])
    print("RESULT: CPU OK")
