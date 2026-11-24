"""Talks to the LIVE pet server over a second, silent connection (typed text, real brain, real voice synthesis).

Her answers come back to this socket only: nothing is played on the PC, except what a real task
reports when it finishes (that goes to every client, as always). The turns stay in her memory.
Usage: python live_ws_check.py <words> [<more words> ...]
"""
import asyncio
import json
import sys
import time

import websockets

sys.stdout.reconfigure(encoding="utf-8")
URL = "ws://127.0.0.1:12393/client-ws"


async def turn(ws, text):
    t0 = time.time()
    await ws.send(json.dumps({"type": "text-input", "text": text, "images": []}))
    said, errors, first, actions = [], [], None, []
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
            if msg.get("actions"):
                actions.append(msg["actions"])
        elif kind == "pet-action":
            actions.append(msg.get("motions"))
        elif kind == "error":
            errors.append(msg.get("message"))
        elif kind == "backend-synth-complete":
            await ws.send(json.dumps({"type": "frontend-playback-complete"}))
        elif kind == "control" and msg.get("text") == "conversation-chain-end":
            break
    print(f"你：{text}")
    print(f"小克：{''.join(said)}")
    print(f"      first sound after {first and round(first, 1)} s, done in {time.time() - t0:.1f} s, errors: {errors}, actions: {actions}")


async def main():
    async with websockets.connect(URL, max_size=None) as ws:
        await asyncio.sleep(1.5)  # let the greeting messages arrive
        for words in sys.argv[1:]:
            await turn(ws, words)


asyncio.run(main())
