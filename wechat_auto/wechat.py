"""[deskpet] WeChat auto-reply, part 4: look at the WeChat 4.2 window. It only looks: no clicks, no typing.

WeChat exposes nothing to UI Automation, so this works on a capture of that one window, in memory:
nothing is saved and no chat content goes to a model.

  - whose chat is open: the title's shape must match the glyph saved in target_name.npy (OCR
    misreads a lone character, and "contains 贺" would be the wrong test anyway: "贺子", "贺(12)")
  - a Bilibili share from the other side: a grey bubble on the left, card-sized, with the pink
    Bilibili icon in its bottom-left corner
  - whether the input box is empty, so a draft of the user's is never sent along

Measured on 2026-11-22 at 125% scaling. A different scaling, theme or WeChat layout makes the
checks fail, which means "do nothing", never "send anyway".
"""

import ctypes
import hashlib
from ctypes.wintypes import DWORD
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import win32gui
import win32ui

import watcher

WINDOW_CLASS = "Qt51514QWindowIcon"
NAME_FILE = Path(__file__).with_name("target_name.npy")

# physical pixels
MAIN_MIN_WIDTH = 600               # narrower = a login window, never the main one
TITLE_TOP, TITLE_BOTTOM = 44, 92
TITLE_LEFT, TITLE_RIGHT = 8, 600   # from the chat pane's left edge
MESSAGES_TOP = 153                 # measured on the real window: 151 is the line under the title
INPUT_HEIGHT = 190                 # input box + margin, from the bottom of the window
INPUT_TEXT = (28, 182, 30, 75)     # left margin, top (from bottom), right margin, bottom (from bottom)
BUBBLE_X = (88, 98)                # a column of a left-hand bubble left of its content (the icon starts at 99)
CARD_WIDTH = (270, 340)
CARD_MIN_HEIGHT = 110
KEY_LINES_START = 56             # lines of a card starting above this row make its key (17, 40 or 47; next 67)
THUMBNAIL = (37, 226)              # in a card, from this row and column on: the thumbnail (43, 235)
OWN_AVATAR_X = (80, 48)            # a column through our avatars, from the window's right edge
THEIR_AVATAR_X = (34, 66)          # the same through their avatars, from the pane's left edge
OWN_AVATAR_MIN = 20                # rows of it that make one avatar
EDGE = 3                           # a bubble starting this close under the top is cut off
HINT_GREY = 140                    # the empty box's hint is lighter than this, typed text much darker
CARET_X = 6                        # the caret of an empty box is within this of the left margin
INK = 45                           # this different from the background = part of a character
# Overlap needed with the saved glyph. Of all 6763 GB2312 characters the closest wrong one reaches
# 0.51; the name itself 0.68-0.80 in other colours. The chat list only decides where to click, the
# open chat's title decides whether anything may be sent, so only the title needs the strict value.
SAME_NAME = 0.85
SAME_NAME_IN_LIST = 0.62
LIST_NAME_X = (-230, -84)          # names in the chat list, from the chat pane's left edge


@dataclass(frozen=True)
class Card:
    left: int
    top: int
    right: int
    bottom: int
    key: str  # stays the same for the same card, so it is never answered twice

    @property
    def centre(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2


def find_window() -> int | None:
    found = []

    def each(hwnd, _):
        if win32gui.GetClassName(hwnd) == WINDOW_CLASS and win32gui.IsWindowVisible(hwnd):
            pid = DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if watcher.process_name(pid.value) == watcher.APP and not win32gui.IsIconic(hwnd):
                left, _, right, _ = win32gui.GetWindowRect(hwnd)
                if right - left >= MAIN_MIN_WIDTH:
                    found.append(hwnd)
        return True

    win32gui.EnumWindows(each, None)
    return found[0] if len(found) == 1 else None  # two windows = not sure which: do nothing


def capture(hwnd: int) -> np.ndarray:
    """The window in physical pixels, height x width x RGB."""
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    # this thread only: the pet's own windows keep their scaling
    before = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        w, h = right - left, bottom - top
        window_dc = win32gui.GetWindowDC(hwnd)
        src = win32ui.CreateDCFromHandle(window_dc)
        mem = src.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        try:
            bmp.CreateCompatibleBitmap(src, w, h)
            mem.SelectObject(bmp)
            if not user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2):
                raise OSError("PrintWindow failed")
            raw = np.frombuffer(bmp.GetBitmapBits(True), np.uint8).reshape(h, w, 4)
            return raw[:, :, 2::-1].astype(np.int16)  # BGRA -> RGB
        finally:
            mem.DeleteDC()
            src.DeleteDC()
            win32gui.ReleaseDC(hwnd, window_dc)
            win32gui.DeleteObject(bmp.GetHandle())
    finally:
        user32.SetThreadDpiAwarenessContext(before)


def pane_left(img: np.ndarray) -> int:
    """Left edge of the chat pane: the title bar is one flat colour from there to the right."""
    row = img[TITLE_TOP]
    start = img.shape[1] - 200
    differs = np.abs(row[:start] - row[start]).max(axis=1) > 3
    edge = np.nonzero(differs)[0]
    return int(edge[-1]) + 1 if len(edge) else 0


def ink(area: np.ndarray) -> np.ndarray:
    background = np.median(area.reshape(-1, 3), axis=0)
    return np.abs(area - background).max(axis=2) > INK


def strokes(area: np.ndarray) -> np.ndarray:
    """Characters by their own contrast: a name looks the same dark on grey or white on green."""
    background = np.median(area.reshape(-1, 3), axis=0)
    diff = np.abs(area - background).max(axis=2)
    top = float(diff.max())
    return diff > max(INK, 0.5 * top)


def trimmed(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return np.zeros((0, 0), bool)
    return mask[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]


def title_shape(img: np.ndarray) -> np.ndarray:
    x = pane_left(img)
    return trimmed(strokes(img[TITLE_TOP:TITLE_BOTTOM, x + TITLE_LEFT: x + TITLE_RIGHT]))


def same_shape(shape: np.ndarray, name: np.ndarray, needed: float = SAME_NAME) -> bool:
    """The whole title is this name: same size (nothing before or after it) and same strokes."""
    if not shape.size or any(abs(a - b) > 1 for a, b in zip(shape.shape, name.shape)):
        return False
    h, w = max(shape.shape[0], name.shape[0]), max(shape.shape[1], name.shape[1])
    a, b = np.zeros((h + 2, w + 2), bool), np.zeros((h + 2, w + 2), bool)
    b[1: 1 + name.shape[0], 1: 1 + name.shape[1]] = name
    best = 0.0
    for dy in range(3):  # a pixel of slack for where the glyph starts
        for dx in range(3):
            if dy + shape.shape[0] > h + 2 or dx + shape.shape[1] > w + 2:
                continue
            a[:] = False
            a[dy: dy + shape.shape[0], dx: dx + shape.shape[1]] = shape
            best = max(best, float((a & b).sum() / (a | b).sum()))
    return best >= needed


def is_target_chat(img: np.ndarray) -> bool:
    return NAME_FILE.exists() and same_shape(title_shape(img), np.load(NAME_FILE))


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.nonzero(edges == 1)[0].tolist(), np.nonzero(edges == -1)[0].tolist()))


def target_row(img: np.ndarray) -> tuple[int, int] | None:
    """Where the target's line is in the chat list; None unless exactly one line is that name."""
    pane = pane_left(img)
    x0, x1 = pane + LIST_NAME_X[0], pane + LIST_NAME_X[1]
    if x0 < 0 or not NAME_FILE.exists():
        return None
    band = img[:, x0:x1]
    # each row against its own colour: the selected conversation has a green background
    inked = (np.abs(band - np.median(band, axis=1, keepdims=True)).max(axis=2) > INK).any(axis=1)
    inked[:TITLE_BOTTOM] = False
    name, found = np.load(NAME_FILE), []
    for a, b in runs(inked):
        if 11 <= b - a <= 24 and same_shape(trimmed(strokes(band[a:b])), name, SAME_NAME_IN_LIST):
            found.append(((x0 + x1) // 2, (a + b) // 2))
    return found[0] if len(found) == 1 else None


def text_key(area: np.ndarray) -> str:
    """A card's identity from its first lines of text, each line by itself.

    At 125% scaling WeChat draws every line pixel for pixel the same at any height, but rounds each
    one's own position: the gaps between lines change by a pixel with where the card is on the screen
    (measured 2026-11-22 on a real card at 24 heights). So the gaps are not part of the key.
    """
    mask = ink(area)
    digest = hashlib.sha256()
    for a, b in runs(mask.any(axis=1)):
        if a + 6 >= KEY_LINES_START:  # the area starts 6 rows into the card
            break
        line = trimmed(mask[a:b])
        digest.update(repr(line.shape).encode() + np.packbits(line).tobytes())
    return digest.hexdigest()[:20]


def incoming_bilibili_cards(img: np.ndarray) -> list[Card]:
    """Bilibili share cards from the other side, oldest first."""
    pane = pane_left(img)
    top, bottom = MESSAGES_TOP, img.shape[0] - INPUT_HEIGHT
    background = img[TITLE_TOP, img.shape[1] - 200]
    column = np.median(img[top:bottom, pane + BUBBLE_X[0]: pane + BUBBLE_X[1]], axis=1)
    darker = background - column
    bubble = (darker.min(axis=1) >= 5) & (darker.max(axis=1) <= 25)  # the light grey of their bubbles
    # close the gaps that lines of text make in the grey
    for a, b in runs(~bubble):
        if 0 < a and b < len(bubble) and b - a <= 6:
            bubble[a:b] = True

    cards = []
    for a, b in runs(bubble):
        if a <= EDGE or b >= len(bubble):
            continue  # cut off by the edge: its key would differ and an answered card would look new
        if b - a < CARD_MIN_HEIGHT:
            continue
        y0, y1 = top + a, top + b
        row = img[y0 + 5, pane + BUBBLE_X[0]:]
        diff = background - row
        grey = (diff.min(axis=1) >= 5) & (diff.max(axis=1) <= 25)
        end = int(np.argmin(grey)) if not grey.all() else len(grey)
        x0, x1 = pane + BUBBLE_X[0], pane + BUBBLE_X[0] + end
        if not CARD_WIDTH[0] <= x1 - x0 <= CARD_WIDTH[1]:
            continue
        r, g, b_ = np.moveaxis(img[y1 - 38: y1, x0: x0 + 40], 2, 0)
        pink = (r > 215) & (g < 170) & (r - g > 70) & (b_ > 110) & (b_ - g > 10)
        if pink.sum() < 60:
            continue
        # the text part only: the thumbnail loads late and would change the key
        area = img[y0 + 6: y0 + 90, x0: x1 - 6].copy()
        # with a title of one line the thumbnail reaches up into this area: painted over
        area[THUMBNAIL[0] - 6:, THUMBNAIL[1]:] = np.median(img[y0 + 8: y0 + 14, x0: x1 - 6].reshape(-1, 3), axis=0)
        key = text_key(area)
        cards.append(Card(x0, y0, x1, y1, key))
    return cards


def _avatar_tops(img: np.ndarray) -> list[int]:
    """Where each message on the screen starts, from both sides: one avatar per message."""
    h, w = img.shape[:2]
    pane, background = pane_left(img), img[TITLE_TOP, w - 200]
    tops = []
    for x0, x1 in ((w - OWN_AVATAR_X[0], w - OWN_AVATAR_X[1]), (pane + THEIR_AVATAR_X[0], pane + THEIR_AVATAR_X[1])):
        column = img[MESSAGES_TOP: h - INPUT_HEIGHT, x0:x1]
        filled = (np.abs(column - background).max(axis=2) > 7).mean(axis=1) > 0.5
        for a, b in runs(~filled):
            if 0 < a and b < len(filled) and b - a <= 6:
                filled[a:b] = True
        # cut off at the top = not seen, exactly like a card there
        tops += [MESSAGES_TOP + a for a, b in runs(filled) if a > EDGE and b - a >= OWN_AVATAR_MIN]
    return sorted(tops)


def message_count(img: np.ndarray) -> int:
    """How many messages are whole on the screen."""
    return len(_avatar_tops(img))


def messages_below(img: np.ndarray, key: str) -> int | None:
    """How many messages, anyone's, came after that card; None if it isn't on the screen.

    Unlike pixels this number doesn't change with the window's size or with lines that wrap differently.
    """
    cards = [c for c in incoming_bilibili_cards(img) if c.key == key]
    if not cards:
        return None
    return sum(1 for top in _avatar_tops(img) if top >= cards[-1].bottom)


def own_messages_below(img: np.ndarray, key: str) -> int | None:
    """How many messages from our side are under that card; None if it isn't on the screen.

    Counted by our avatar, which a photo, a sticker and a voice message have as well as text.
    """
    cards = [c for c in incoming_bilibili_cards(img) if c.key == key]
    if not cards:
        return None
    h, w = img.shape[:2]
    column = img[cards[-1].bottom: h - INPUT_HEIGHT, w - OWN_AVATAR_X[0]: w - OWN_AVATAR_X[1]]
    if not column.size:
        return 0
    background = img[TITLE_TOP, w - 200]
    filled = (np.abs(column - background).max(axis=2) > 7).mean(axis=1) > 0.5
    for a, b in runs(~filled):
        if 0 < a and b < len(filled) and b - a <= 6:
            filled[a:b] = True  # a pale stripe inside one picture
    return sum(1 for a, b in runs(filled) if b - a >= OWN_AVATAR_MIN)


def input_is_empty(img: np.ndarray) -> bool:
    left, top, right, bottom = INPUT_TEXT
    h, w = img.shape[:2]
    area = img[h - top: h - bottom, pane_left(img) + left: w - right]
    marks = ink(area)
    r, g, b = np.moveaxis(area, 2, 0)
    spread = area.max(axis=2) - area.min(axis=2)
    # with the focus, an empty box shows a light grey hint ("长按鼠标 语音输入") after a green caret;
    # anything dark or coloured (typed text, emoji, a picture) is a draft
    hint = (area.min(axis=2) >= HINT_GREY) & (spread <= 30)
    caret = (g > r + 20) & (g >= b)
    caret[:, CARET_X:] = False
    return int((marks & ~hint & ~caret).sum()) < 5
