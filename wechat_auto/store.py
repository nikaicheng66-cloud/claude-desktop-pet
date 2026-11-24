"""[deskpet] WeChat auto-reply, part 10: what is kept on disk, in wechat_auto/state/.

  enabled        exists = the feature is on (delete it, or `worker.py off`, to stop it)
  pending        a message sound that has not been looked into yet
  handled.json   every card seen, by key and by video id, so nothing is answered twice
  replies/       progress of each reply (reply.py), so an interrupted one carries on
  worker.log     what happened; no names and no message text
"""

import json
import os
import time
from pathlib import Path

STATE = Path(__file__).resolve().parent / "state"
WORKING, DONE, FAILED, OLD, REPEAT = "working", "done", "failed", "old", "repeat"
YOURS = "yours"  # the user was writing himself: not for the pet to take over


def enabled() -> bool:
    return (STATE / "enabled").exists()


def replies_on() -> bool:
    """Off = mute only (the user, 2026-11-23: 「把自动回复关了，就留一个静音的」): the message sound while
    he is away still sets the volume to 0, but WeChat is never opened and nothing is sent."""
    return not (STATE / "replies_off").exists()


def set_replies(on: bool) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    if on:
        (STATE / "replies_off").unlink(missing_ok=True)
    else:
        (STATE / "replies_off").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")


def set_enabled(on: bool) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    if on:
        (STATE / "enabled").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    else:
        (STATE / "enabled").unlink(missing_ok=True)


def log(text: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "worker.log").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")


class Handled:
    """The memory of what was answered. Saved before acting, never half written."""

    def __init__(self, folder: Path | None = None):
        self.folder = folder or STATE
        self.path = self.folder / "handled.json"
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        # an unreadable file raises above on purpose: an empty memory would answer old videos again
        self.cards: dict[str, dict] = data.get("cards", {})
        self.videos: dict[str, str] = data.get("videos", {})  # video id -> card key
        # The most messages ever seen whole at one look. Every card that then had fewer messages below
        # it was noted, and that number only grows: an unknown card with this many below it is old.
        self.seen: int | None = data.get("seen")

    @property
    def replies(self) -> Path:
        return self.folder / "replies"

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cards": self.cards, "videos": self.videos, "seen": self.seen}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def unfinished(self) -> list[str]:
        return [k for k, c in self.cards.items() if c.get("status") == WORKING]

    def start(self, key: str) -> None:
        self.cards[key] = {"status": WORKING, "since": time.strftime("%Y-%m-%d %H:%M:%S"), "tries": 0}
        self.save()

    def finish(self, key: str, status: str, why: str = "") -> None:
        self.cards[key].update(status=status, why=why)
        self.save()

    def mark_old(self, keys) -> int:
        new = [k for k in keys if k not in self.cards]
        for k in new:
            self.cards[k] = {"status": OLD}
        self.save()
        return len(new)

    def count_ours(self) -> None:
        """A message of ours went out: it now lies under every card that is still unfinished."""
        for key in self.unfinished():
            self.cards[key]["ours"] = self.cards[key].get("ours", 0) + 1
        self.save()

    def claim_video(self, key: str, vid: str) -> bool:
        """False = this video was answered (or is being answered) for another card."""
        if self.videos.get(vid, key) != key:
            return False
        self.videos[vid] = key
        self.cards[key]["video"] = vid
        self.save()
        return True
