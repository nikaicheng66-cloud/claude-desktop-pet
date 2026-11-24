"""[deskpet] WeChat auto-reply, part 3: play the video in the browser and write down what is said.

The browser plays the page normally, exactly as if the link had been opened by hand. Nothing is
fetched or scraped from the site: only what this PC's speakers are playing is listened to, locally
(deskpet/echo_gate's loopback buffer, which is taken before the master volume, so volume 0 works).
A page that won't play (captcha, login, autoplay blocked) ends as CannotReply; nothing is worked around.

The video gets a browser window of its own, and that window is the only one ever closed.
Only runs while the user is away; as soon as he is back it stops.
"""

import ctypes
import os
import re
import subprocess
import time
import winreg
from ctypes.wintypes import DWORD

import numpy as np
import win32con
import win32gui

import eyes
import screen
import video
import watcher

SR = 16000
BROWSER = "msedge.exe"  # this PC's default for https
PAGE_WITHIN = 20.0   # seconds for the page to load
STEP = 5.0           # seconds of audio collected at a time (the loopback buffer keeps 30)
CHECK = 0.25         # how often to look whether autoplay moved on
LAG = 0.5            # leave the newest audio until the next step: it may still be arriving
START_WITHIN = 30.0  # no sound this long after opening = it isn't playing
END_SILENCE = 25.0   # this long silent after it played = finished
MAX_SECONDS = 20 * 60
SURE_LANGUAGE = 0.7  # less sure of the detected language than this = take it as Chinese
SOUND = 5e-4         # RMS above this = something is playing
COUNTDOWN = 3.0      # at least this long silent before autoplay starts the next video (measured: 6.7 s)
NEXT_MAX = 8.0       # the title changes at most this long after the next video became audible (measured: 0.9 s)


# what whisper invents from music and silence
_INVENTED = re.compile(r"独播剧场|YoYo Television|李宗盛|中文字幕|Amara|请不吝|Thanks for watching|订阅|点赞.{0,6}转发|打赏支持|明镜与点点|字幕由|字幕志愿者|字幕作成|字幕制作|谢谢观看|感谢观看|以下是普通话"
                       r"|subtitles? by|thank you for watching|ご視聴ありがとう|시청해 ?주셔서", re.I)



class UserIsBack(Exception):
    """Not a failure: try again the next time he is away."""


def browser_path() -> str:
    key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{BROWSER}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key) as k:
                path = winreg.QueryValueEx(k, "")[0].strip('"')
            if os.path.isfile(path):
                return path
        except OSError:
            continue
    raise video.CannotReply("browser not found")


def browser_windows() -> set[int]:
    found = set()

    def each(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            pid = DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if watcher.process_name(pid.value) == BROWSER:
                found.add(hwnd)
        return True

    win32gui.EnumWindows(each, None)
    return found


def title_of(hwnd: int) -> str:
    return win32gui.GetWindowText(hwnd) if win32gui.IsWindow(hwnd) else ""


def until_autoplay(audio: np.ndarray) -> np.ndarray:
    """This video's part of a recording that ended because autoplay moved on.

    The next video is already audible when the title changes. In between lies the countdown's
    silence: cut there. Without that gap the two can't be told apart, and a summary of the wrong
    video must not be sent, so then there is no reply.
    """
    hop = SR // 10
    quiet = np.array([np.sqrt(np.mean(audio[i:i + hop] ** 2)) <= SOUND
                      for i in range(0, len(audio) - hop + 1, hop)], dtype=np.int8)
    edges = np.diff(np.concatenate(([0], quiet, [0])))
    for a, b in reversed(list(zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]))):
        if (len(quiet) - b) / 10 > NEXT_MAX:
            break  # further back is inside this video
        if a and (b - a) / 10 >= COUNTDOWN:
            return audio[:a * hop]
    raise video.CannotReply("could not tell where the video ended and the next one began")


def transcriber(model):
    """transcribe() for listen(), from a faster-whisper model (the pet's own can be shared).

    No VAD filter: on speech over music it threw the whole video away.
    The language is detected (the user's rule 2026-11-22). When unsure it is taken as Chinese, the
    usual one here; music alone is often called English, with words too unsure to pass the filter.
    """
    def transcribe(audio: np.ndarray) -> str:
        loud = np.nonzero(np.abs(audio) > SOUND)[0]
        if not len(loud):
            return ""
        # without the silence around it: whisper makes up credits there
        audio = audio[max(0, loud[0] - SR // 5): loud[-1] + SR // 5]
        options = dict(beam_size=5, vad_filter=False, condition_on_previous_text=False)
        segments, info = model.transcribe(audio, language_detection_segments=4, **options)  # lazy, nothing yet
        if info.language == "zh" or info.language_probability < SURE_LANGUAGE:
            segments, info = model.transcribe(audio, language="zh", initial_prompt="以下是普通话的句子。", **options)
        return "".join(s.text for s in segments
                       if s.no_speech_prob < 0.6 and s.avg_logprob > -0.8 and not _INVENTED.search(s.text))

    return transcribe


class Page:
    """One video page in a window of its own. It is known by its address: titles differ from video
    to video, not all end in 哔哩哔哩, and anyone's page could say so anyway."""

    def __init__(self, vid: str, check):
        self.vid, self.check, self.hwnd = vid, check, None  # check() raises as soon as he is back

    def __enter__(self):
        address = video.page_url(self.vid)
        before = browser_windows()
        subprocess.Popen([browser_path(), "--new-window", address])
        try:
            self._load(before)
        except BaseException:
            self.close()
            raise
        return self

    def _load(self, before: set[int]) -> None:
        end, last = time.time() + PAGE_WITHIN, None
        while time.time() < end:
            time.sleep(0.5)
            self.check()
            if not self.hwnd:
                new = browser_windows() - before
                if len(new) != 1:
                    continue
                self.hwnd = new.pop()  # appeared on our launch with nobody at the PC: ours to close
            try:
                address = screen.page_address(self.hwnd)
            except Exception:
                continue  # the tree isn't there yet
            if address and not screen.is_bilibili(address):
                raise video.CannotReply("the address left bilibili, closed")
            found = video.video_id(address)
            if not found or (self.vid.startswith("BV") and found != self.vid):
                continue
            title = title_of(self.hwnd)
            if "bilibili.com/video" in title:
                continue  # still the bare address
            if title and title == last:
                return  # loaded: the title is final
            last = title
        raise video.CannotReply("the video page did not open (captcha, login or no network)")

    def close(self) -> None:
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception as e:
                print(f"[deskpet] could not close the video's window: {e}", flush=True)

    def __exit__(self, *_) -> None:
        self.close()


def video_title(window_title: str) -> str:
    """The window's title without the browser's and the site's endings."""
    name = re.sub(r"(?: - [^-]{1,24})? - Microsoft\W*Edge$", "", window_title)
    return name.split("_哔哩哔哩")[0]


def record(window, title, may_continue, clock=time.time, sleep=time.sleep, since=None,
           look=lambda: None) -> np.ndarray:
    """Collect speaker audio until the video is over.

    window(start, end): 16 kHz mono speaker audio between two wall-clock times
    title():            current title of the video's window; a change = next video or closed
    since:              when the page was opened: it starts playing before its title is there
    """
    began = clock()
    done_until = began if since is None else since
    first_title = title()
    parts, last_sound = [], None
    while True:
        waited, moved_on = 0.0, False
        while waited < STEP and not moved_on:
            sleep(CHECK)
            waited += CHECK
            if not may_continue():
                raise UserIsBack()
            moved_on = title() != first_title
            if not moved_on:
                look()
        if moved_on:  # autoplay moved on: keep this video's last words, nothing of the next one
            end = clock() - CHECK
            if end > done_until:
                chunk = window(done_until, end)
                parts.append(chunk)
                if float(np.sqrt(np.mean(chunk**2))) > SOUND:
                    last_sound = end
            break
        now = clock()
        chunk = window(done_until, now - LAG)
        done_until = now - LAG
        parts.append(chunk)
        if float(np.sqrt(np.mean(chunk**2))) > SOUND:
            last_sound = now
        if last_sound is None and now - began >= START_WITHIN:
            raise video.CannotReply("the video did not start playing")
        if last_sound is not None and now - last_sound >= END_SILENCE:
            break
        if now - began >= MAX_SECONDS:
            raise video.CannotReply("the video is longer than 20 minutes")  # no summary of half a video
    if last_sound is None:
        raise video.CannotReply("nothing was played")
    audio = np.concatenate(parts).astype(np.float32)
    return until_autoplay(audio) if moved_on else audio


def listen(url: str, window, transcribe, away=None) -> tuple[str, str, list[bytes]]:
    """Open the video, listen and look to the end, close it: (transcript, title, PNG pictures).

    away: send.away when our own click came just before, which resets the plain idle time.
    """
    vid = video.video_id(url)
    if not vid:
        raise video.CannotReply("not a Bilibili video link")
    if not (away or watcher.may_take_screen)():  # looked up now, not when the module was imported
        raise UserIsBack()
    idle_at_open, opened = watcher.idle_seconds(), time.time()

    # The browser taking the front is not user input, so the idle time keeps counting. The page
    # itself may go full screen, so only presence and the lock screen are checked while it plays.
    def still_away() -> bool:
        return (watcher.idle_seconds() >= idle_at_open + (time.time() - opened) - 2
                and not watcher.screen_locked())  # any input since opening = he is back

    def check() -> None:
        if not still_away():
            raise UserIsBack()

    with Page(vid, check) as page:  # only an address rebuilt from the checked id is opened
        name = video_title(title_of(page.hwnd))  # to search similar ones with
        seen = eyes.Eyes(page.hwnd, lambda: title_of(page.hwnd))
        audio = record(window, lambda: title_of(page.hwnd), still_away, since=opened, look=seen.look)
    # the recording runs from `opened` on: where its last sound is, the video ended
    loud = np.nonzero(np.abs(audio) > SOUND)[0]
    until = opened + (loud[-1] / SR if len(loud) else 0)
    return transcribe(audio), name, seen.pictures(until)
