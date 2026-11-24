"""Asks the LIVE pet server about a picture over a second, silent connection.

Her answer comes back to this socket only (nothing is played on the PC). No Origin header is sent,
which is what the server's origin guard expects from a local program.
Usage: python live_ws_test.py <picture> <words> [<follow-up words without picture>]
"""
import asyncio
import base64
import json
import sys
import time

import websockets

URL = "ws://127.0.0.1:12393/client-ws"


async def turn(ws, text, images):
    t0 = time.time()
    await ws.send(json.dumps({"type": "text-input", "text": text, "images": images}))
    said, errors, first = [], [], None
    while True:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
        except asyncio.TimeoutError:
            errors.append("timeout")
            break
        kind = msg.get("type")
        if kind == "audio":
            if first is None:
                first = time.time() - t0
            said.append((msg.get("display_text") or {}).get("text", ""))
        elif kind == "error":
            errors.append(msg.get("message"))
        elif kind == "backend-synth-complete":
            await ws.send(json.dumps({"type": "frontend-playback-complete"}))
        elif kind == "control" and msg.get("text") == "conversation-chain-end":
            break
    print(f"你：{text}" + ("  [+图片]" if images else ""))
    print(f"小克：{''.join(said)}")
    print(f"      first words after {first and round(first, 1)} s, done in {time.time() - t0:.1f} s, errors: {errors}")


async def main():
    path, words = sys.argv[1], sys.argv[2]
    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    data = f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()
    async with websockets.connect(URL, max_size=None) as ws:
        await asyncio.sleep(1.5)  # let the greeting messages arrive
        await turn(ws, words, [{"source": "upload", "data": data, "mime_type": mime}])
        for more in sys.argv[3:]:
            await turn(ws, more, [])


asyncio.run(main())
