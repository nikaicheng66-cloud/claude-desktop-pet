"""[deskpet] WeChat auto-reply, part 13: a few still pictures of the video while it plays.

The user's rule (2026-11-22): summarise from sound + screenshots + title, because many of the
videos have no speech and say what they say in burned-in subtitles.

What is captured is only the 16:9 picture inside Bilibili's player, in the window we opened
ourselves: no tabs, no account corner, no input bar, and nothing at all if that box isn't found.
The pictures stay in memory and are never written to disk.
"""

import contextlib
import ctypes
import struct
import time
import zlib

import comtypes
import comtypes.client
import numpy as np
import win32gui

import wechat

PLAYER = "bpx-player-primary-area"  # UI Automation class: the picture + the bar under it
EVERY = 1.5         # seconds between pictures; doubles whenever KEEP is full (long videos)
KEEP = 48           # most held in memory
PICTURES = 12       # most given to the model, spread over the video
MAX_WIDTH = 640
MIN_SIDE = 150
END_MARGIN = 0.3    # seconds left out at the end: the end screen advertises other videos
BAR = 16            # darker than this (median of a column or row) = a black bar
BLANK = 6.0         # standard deviation below this = an empty picture


@contextlib.contextmanager
def _physical():
    # not screen.physical(): that also moves the cursor back, and this runs all through the video
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    before = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        yield
    finally:
        user32.SetThreadDpiAwarenessContext(before)


def player_box(hwnd: int) -> tuple[int, int, int, int] | None:
    """The player in physical screen pixels, looked up each time: the page's layout moves."""
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA

    uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    wanted = uia.CreatePropertyCondition(UIA.UIA_ClassNamePropertyId, PLAYER)
    found = uia.ElementFromHandle(hwnd).FindFirst(UIA.TreeScope_Descendants, wanted)
    if not found or found.CurrentIsOffscreen:
        return None
    r = found.CurrentBoundingRectangle
    return r.left, r.top, r.right, r.bottom


def picture_part(img: np.ndarray, window: tuple, box: tuple) -> np.ndarray | None:
    """Only the video's picture out of a capture of the whole window; None if that isn't certain."""
    left, top, right, bottom = box
    bottom = min(bottom, top + (right - left) * 9 // 16)  # under it is the bar to type comments in
    x0, y0, x1, y1 = left - window[0], top - window[1], right - window[0], bottom - window[1]
    if x0 < 0 or y0 < 0 or x1 > img.shape[1]:
        return None
    y1 = min(y1, img.shape[0])
    if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
        return None
    part = without_bars(img[y0:y1, x0:x1]).astype(np.uint16)
    step = -(-part.shape[1] // MAX_WIDTH)  # averaged, so that subtitles stay readable
    if step > 1:
        h, w = part.shape[0] // step * step, part.shape[1] // step * step
        part = part[:h, :w].reshape(h // step, step, w // step, step, 3).mean(axis=(1, 3))
    return part.astype(np.uint8)


def without_bars(part: np.ndarray) -> np.ndarray:
    """A portrait video fills a third of the player: without its bars the subtitles keep their size
    (shrunk with them, 换位 was read as 搬位). The bars also carry comments only. Equal on both sides."""
    bright = part.max(axis=2)

    def bar(line_medians: np.ndarray) -> int:
        lit = np.nonzero(line_medians >= BAR)[0]
        return int(min(lit[0], len(line_medians) - 1 - lit[-1])) if len(lit) else 0

    x = bar(np.median(bright, axis=0))
    if part.shape[1] - 2 * x >= MIN_SIDE:
        part, bright = part[:, x:part.shape[1] - x], bright[:, x:part.shape[1] - x]
    y = bar(np.median(bright, axis=1))
    if part.shape[0] - 2 * y >= MIN_SIDE:
        part = part[y:part.shape[0] - y]
    return part


def grab(hwnd: int) -> np.ndarray | None:
    with _physical():
        box = player_box(hwnd)
        if not box:
            return None
        window = win32gui.GetWindowRect(hwnd)
        img = wechat.capture(hwnd)
        if win32gui.GetWindowRect(hwnd) != window or player_box(hwnd) != box:
            return None  # it moved meanwhile: the crop could show something else
    return picture_part(img, window, box)


def png(img: np.ndarray) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    h, w = img.shape[:2]
    rows = b"".join(b"\0" + img[y].tobytes() for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class Eyes:
    """look() as often as you like; pictures() afterwards."""

    def __init__(self, hwnd: int, title, take=grab, clock=time.time):
        self.hwnd, self.title, self.take, self.clock = hwnd, title, take, clock
        self.first_title = title()
        self.every, self.last = EVERY, float("-inf")
        self.kept: list[tuple[float, np.ndarray]] = []

    def look(self) -> None:
        now = self.clock()
        if now - self.last < self.every:
            return
        self.last = now
        try:
            if self.title() != self.first_title:
                return
            img = self.take(self.hwnd)
            if img is None or img.std() < BLANK or self.title() != self.first_title:
                return  # nothing to see, or autoplay moved on while looking
        except Exception as e:  # without pictures there is still the sound
            print(f"[deskpet] no picture of the video: {e}", flush=True)
            return
        self.kept.append((now, img))
        if len(self.kept) >= KEEP:
            self.kept = self.kept[::2]
            self.every *= 2

    def pictures(self, until: float) -> list[bytes]:
        """Spread over the video; none from after `until` (countdown, end screen, the next video)."""
        own = [img for at, img in self.kept if at <= until - END_MARGIN]
        if len(own) > PICTURES:
            own = [own[i] for i in np.linspace(0, len(own) - 1, PICTURES).round().astype(int)]
        return [png(img) for img in own]
