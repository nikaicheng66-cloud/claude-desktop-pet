"""[deskpet] WeChat auto-reply, part 5: send one exact text to the target's chat.

The only module that touches mouse, keyboard or clipboard. Plain input, no imitation of a human.
Before the one click on 发送 all of these must hold, otherwise nothing is sent:
  - the user is away: idle long enough, or the last input was our own and nothing since
  - the open chat's title is exactly the target (checked again just before the click)
  - the input box was empty, so no draft of the user's goes along
  - what is in the box, copied back out, is exactly the text
  - the point about to be clicked belongs to the WeChat window, and WeChat has the focus
No click is ever repeated: if a result is unclear, that is reported instead of sending again.
There are no random pauses or other attempts to look human to WeChat.
"""

import ctypes
import time
from ctypes.wintypes import DWORD, UINT

import win32api
import win32clipboard as cb
import win32con
import win32gui

import watcher
import wechat

INPUT_POINT = (60, 130)   # from the pane's left edge, from the window's bottom
SEND_POINT = (64, 51)     # from the window's right and bottom edges
CF_TEXT_KINDS = {cb.CF_UNICODETEXT, cb.CF_TEXT, cb.CF_OEMTEXT, cb.CF_LOCALE}
CF_IMAGE_KINDS = {cb.CF_DIB, cb.CF_BITMAP, cb.CF_DIBV5}


class NotSent(Exception):
    """Stopped before the send click: certain that nothing was sent, so it may be tried again."""


class Unclear(Exception):
    """The send click may have been made and could not be confirmed. Never retry."""


def _last_input() -> int:
    class LastInput(ctypes.Structure):
        _fields_ = [("cbSize", UINT), ("dwTime", DWORD)]

    info = LastInput(ctypes.sizeof(LastInput), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise NotSent("cannot tell whether the user is away")
    return info.dwTime


_our_last_input: int | None = None


def away() -> bool:
    """He is away. Our own clicks reset Windows' idle time, so an idle time that started with
    our input still counts; anything he does afterwards changes the tick and ends it."""
    if watcher.may_take_screen():
        return True
    return (_our_last_input is not None and _last_input() == _our_last_input
            and not watcher.screen_locked() and not watcher.fullscreen_busy())


def _open_clipboard() -> None:
    for _ in range(20):
        try:
            cb.OpenClipboard()
            return
        except Exception:  # another program has it open for a moment
            time.sleep(0.05)
    raise NotSent("the clipboard is busy")


def _save_clipboard() -> tuple[int, object] | None:
    """What has to be put back afterwards; refuses what it could not put back (files etc.)."""
    _open_clipboard()
    try:
        kinds, kind = set(), cb.EnumClipboardFormats(0)
        while kind:
            kinds.add(kind)
            kind = cb.EnumClipboardFormats(kind)
        if not kinds:
            return None
        if cb.CF_HDROP in kinds:
            raise NotSent("files are on the clipboard and would be lost")
        if cb.CF_UNICODETEXT in kinds:
            return cb.CF_UNICODETEXT, cb.GetClipboardData(cb.CF_UNICODETEXT)
        if cb.CF_DIB in kinds:
            return cb.CF_DIB, cb.GetClipboardData(cb.CF_DIB)
        raise NotSent("the clipboard holds something that could not be put back")
    finally:
        cb.CloseClipboard()


def _set_clipboard(item: tuple[int, object] | None) -> None:
    _open_clipboard()
    try:
        cb.EmptyClipboard()
        if item:
            cb.SetClipboardData(*item)
    finally:
        cb.CloseClipboard()


def _get_text() -> str:
    _open_clipboard()
    try:
        return cb.GetClipboardData(cb.CF_UNICODETEXT) if cb.IsClipboardFormatAvailable(cb.CF_UNICODETEXT) else ""
    finally:
        cb.CloseClipboard()


def _lines(text: str) -> str:
    text = text.replace("\ufe0f", "").replace("\ufe0e", "")  # invisible: "emoji or plain style"
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


class _Hands:
    """Mouse and keys, only into one window and only while the user keeps off."""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.mine = _last_input()

    def check_user(self) -> None:
        if _last_input() != self.mine:
            raise NotSent("the user is using the PC")

    def _done(self) -> None:
        global _our_last_input
        time.sleep(0.15)
        try:
            self.mine = _our_last_input = _last_input()  # that input was ours
        except NotSent as e:
            raise Unclear(str(e)) from e  # the click is already made

    def owns(self, point: tuple[int, int]) -> bool:
        return win32gui.GetAncestor(win32gui.WindowFromPoint(point), 2) == self.hwnd

    def click(self, point: tuple[int, int]) -> None:
        self.check_user()
        if not self.owns(point):
            raise NotSent("another window covers WeChat")
        win32api.SetCursorPos(point)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        self._done()

    def ctrl(self, key: int) -> None:
        self.check_user()
        if win32gui.GetForegroundWindow() != self.hwnd:
            raise NotSent("WeChat does not have the keyboard focus")
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        try:
            win32api.keybd_event(key, 0, 0, 0)
            win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
        finally:
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        self._done()


def preflight() -> int:
    """The WeChat window, if sending could start. Looks only."""
    hwnd = wechat.find_window()
    if not hwnd:
        raise NotSent("the WeChat window is not visible")
    img = wechat.capture(hwnd)
    if not wechat.is_target_chat(img):
        raise NotSent("the open chat is not the target")
    if not wechat.input_is_empty(img):
        raise NotSent("there is a draft in the input box")
    return hwnd


def _confirm_sent(hwnd: int) -> None:
    for _ in range(10):
        time.sleep(0.5)
        img = wechat.capture(hwnd)
        if wechat.input_is_empty(img) and wechat.is_target_chat(img):
            return
    raise Unclear("clicked 发送, but the input box did not empty")


def send(text: str, before_click=lambda: None) -> None:
    """Returns only when sent. before_click runs just before the click (to save "being sent")."""
    if not away():
        raise NotSent("the user is not away")
    hwnd = preflight()

    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    scaling = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # physical pixels
    cursor = win32api.GetCursorPos()
    flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    saved, changed_clipboard, raised = None, False, False
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        pane = wechat.pane_left(wechat.capture(hwnd))
        box = (left + pane + INPUT_POINT[0], bottom - INPUT_POINT[1])
        button = (right - SEND_POINT[0], bottom - SEND_POINT[1])

        hands = _Hands(hwnd)
        if not (hands.owns(box) and hands.owns(button)):
            # on top just long enough to send; the click gives it the focus
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
            raised = True
            time.sleep(0.4)

        saved = _save_clipboard()
        was_front = win32gui.GetForegroundWindow() == hwnd
        hands.click(box)
        time.sleep(0.4)
        if not was_front:  # that click only activated the window (share.py leaves the browser in front)
            time.sleep(0.4)  # not a double click
            hands.click(box)
            time.sleep(0.4)
        if win32gui.GetForegroundWindow() != hwnd:
            raise NotSent("WeChat did not take the focus")
        if not wechat.input_is_empty(wechat.capture(hwnd)):
            raise NotSent("there is a draft in the input box")

        changed_clipboard = True
        _set_clipboard((cb.CF_UNICODETEXT, text.replace("\n", "\r\n")))
        hands.ctrl(ord("V"))
        time.sleep(0.8)

        _set_clipboard((cb.CF_UNICODETEXT, ""))  # so a failed copy can't look like a match
        hands.ctrl(ord("A"))
        hands.ctrl(ord("C"))
        time.sleep(0.4)
        if _lines(_get_text()) != _lines(text):
            raise NotSent("the input box does not hold exactly the text; left unsent")

        img = wechat.capture(hwnd)
        if not wechat.is_target_chat(img):
            raise NotSent("the chat changed; left unsent")
        if win32gui.GetWindowRect(hwnd) != (left, top, right, bottom):
            raise NotSent("the window moved; left unsent")
        if win32gui.GetForegroundWindow() != hwnd:
            raise NotSent("WeChat lost the focus; left unsent")
        hands.check_user()
        before_click()
        hands.click(button)  # the one click
        _confirm_sent(hwnd)
    finally:
        # Cleaning up must not raise: after a successful click that would read as "not sent"
        # and the message would go out a second time.
        for undo in (
            lambda: changed_clipboard and _set_clipboard(saved),
            lambda: raised and win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags),
            lambda: win32api.SetCursorPos(cursor),
        ):
            try:
                undo()
            except Exception as e:
                print(f"[deskpet] clean-up after sending failed: {e}", flush=True)
        user32.SetThreadDpiAwarenessContext(scaling)
