"""[deskpet] WeChat auto-reply, part 7: the order of one reply.

  watched -> her voice summary -> find one suitable video -> copy its link with Bilibili's share
  arrow (share.py) -> paste and send it, confirm. (WANTED = 1; with more it would find
  the next only after the one before is out.)

Nothing is looked up ahead and nothing waits on purpose: a link goes out when it has been found.

Earlier messages are already out when a later step stops, so every step is saved:
  - Paused: certain that the current message was not sent. run() again later carries on from there.
  - Stuck:  cannot carry on by itself (no suitable video left, or a send whose result is unknown).
            Tell the user. What might have been sent is never sent again.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import send
import share
import video

TRIES = 3  # searches for one link before giving up; results differ from search to search


class Paused(Exception):
    pass


class Stuck(Exception):
    pass


@dataclass
class Progress:
    key: str      # the card this answers (wechat.Card.key)
    source: str   # video id of what he shared
    title: str
    spoken: str
    summary: str
    query: str
    voice_sent: bool = False
    links: list[str] = field(default_factory=list)  # confirmed sent
    sending: str = ""  # set just before a click, cleared once the result is known

    @property
    def done(self) -> bool:
        return self.voice_sent and len(self.links) >= video.WANTED

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"{self.key}.tmp"
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, folder / f"{self.key}.json")  # never a half-written file


def load(folder: Path, key: str) -> Progress | None:
    path = folder / f"{key}.json"
    return Progress(**json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None


def begin(folder: Path, key: str, url: str, title: str, transcript: str, pictures=()) -> Progress:
    """After watching: what to say. Carries on an existing reply to the same card."""
    old = load(folder, key)
    if old:
        return old
    spoken, summary, query = video.prepare(transcript, title, pictures)
    p = Progress(key, video.video_id(url) or "", title, spoken, summary, query)
    p.save(folder)
    return p


def _deliver(p: Progress, folder: Path, what: str, do) -> None:
    def about_to_click() -> None:
        p.sending = what
        p.save(folder)

    try:
        do(about_to_click)
    except send.NotSent as e:
        p.sending = ""
        p.save(folder)
        raise Paused(str(e)) from e
    except Exception as e:
        # before the click it can be tried again; from the click on, nobody knows
        if not p.sending:
            raise Paused(f"{type(e).__name__}: {e}") from e
        raise Stuck(f"unknown whether this was sent, not sending it again: {what}") from e
    p.sending = ""


def run(p: Progress, folder: Path, send_voice, send_link=send.send, find=video.next_similar,
        away=send.away, copy_link=share.link) -> None:
    """send_voice(spoken, before_click) and send_link(text, before_click) return only when sent.

    copy_link(url): what Bilibili's share arrow copies for that video; that text is what is sent.
    """
    if p.sending:
        raise Stuck(f"unknown whether this was sent, not sending it again: {p.sending}")
    if not p.voice_sent:
        if not away():
            raise Paused("the user is back")
        _deliver(p, folder, "voice", lambda mark: send_voice(p.spoken, mark))
        p.voice_sent = True
        p.save(folder)

    while not p.done:
        if not away():
            raise Paused("the user is back")
        used = {p.source, *(video.video_id(u) for u in p.links)}
        url, text = "", ""
        for _ in range(TRIES):
            try:
                found = find(p.query, p.summary, p.title, used)
            except video.CannotReply as e:
                raise Paused(f"looking for a video failed: {e}") from e
            if not found:
                continue
            if not away():
                raise Paused("the user is back")
            url = found[1]
            try:
                text = copy_link(url)
                break
            except share.Unusable:
                used.add(video.video_id(url))  # not this one again, look for another
            except video.CannotReply as e:
                raise Stuck(f"getting the link failed: {e}") from e
            except Exception as e:  # nothing has been sent
                raise Paused(f"getting the link: {type(e).__name__}: {e}") from e
        if not text:
            raise Stuck(f"no suitable video for link {len(p.links) + 1} of {video.WANTED}")
        _deliver(p, folder, url, lambda mark: send_link(text, mark))
        p.links.append(url)
        p.save(folder)
