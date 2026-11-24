"""[deskpet] WeChat auto-reply, part 9: getting to the message.

Bring WeChat's own window up, open the target's chat, scroll to the newest message, click a shared card
to learn its address. Nothing here types or sends. send.NotSent = could not do it now, try again later.

WeChat itself is never started from here: running Weixin.exe while it runs does not bring the
window up, it opens a second instance with a login window (WeChat 4.2, found 2026-11-22).
Nor is a window in the tray shown with ShowWindow: it appears, but WeChat still takes itself for
hidden and ignores clicks and its X. Its own hotkey (Ctrl+Alt+W) does it properly.

The address is read from WeChat's built-in browser through UI Automation (no clipboard). Only the
video id is kept: the rest of that address carries device ids. Only a browser window that appeared
because of our click is ever closed.
"""

import contextlib
import ctypes
import re
import time

import comtypes.client
import numpy as np
import win32api
import win32con
import win32gui
import win32process

import send
import store
import video
import watcher
import wechat

BROWSER_APP, BROWSER_CLASS = "wechatappex.exe", "Chrome_WidgetWin_0"
MAIN_TITLES = ("微信", "Weixin")
SHOW_WITHIN = 8.0
HOTKEY_WITHIN = 3.0
HOTKEY_PROBE, ALREADY_REGISTERED = 0x3A7, 1409
TITLE_STRIP = 18     # y inside the window
PAGE_WITHIN = 20.0
# 2026-11-23 12:07: the card click started WeChat's built-in browser from nothing; its page came ~2 minutes later
PAGE_WITHIN_COLD = 180.0
NOTCHES = 40         # wheel steps at a time (about four screens)
BOTTOM_WITHIN = 180.0  # seconds to get to the newest message, however far up the window was left
STILL_ROUNDS = 3     # this often in a row the wheel moved nothing = the bottom (older parts load late)
SETTLE = 0.6         # between two looks, to tell what moves by itself
SCROLLBAR = 24       # it comes and goes by itself, at the window's right edge
MOVED_ROWS = 4       # more changed rows than this = the wheel moved the messages
LIST_STEP = 2        # wheel steps per look down the chat list: well under a screen, so no line is skipped
LIST_TOP_ROUNDS = 8  # wheel-ups of NOTCHES to get to the top of the chat list
LIST_WITHIN = 120.0  # seconds to search the whole chat list
_BILIBILI = re.compile(r"https?://(?:(?:[a-z0-9-]+\.)*bilibili\.com|b23\.tv)(?:[/?#]|\Z)")
DOCUMENT, VALUE = 50030, 30045  # UI Automation: control type, value property


@contextlib.contextmanager
def physical():
    """Physical pixels for this thread, and the cursor put back afterwards."""
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    before = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    cursor = win32api.GetCursorPos()
    try:
        yield
    finally:
        try:
            win32api.SetCursorPos(cursor)
        except Exception as e:
            print(f"[deskpet] could not put the cursor back: {e}", flush=True)
        user32.SetThreadDpiAwarenessContext(before)


@contextlib.contextmanager
def on_top(hwnd: int):
    flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
    try:
        time.sleep(0.4)
        yield
    finally:
        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)


def _hands(hwnd: int) -> send._Hands:
    if not send.away():
        raise send.NotSent("the user is not away")
    return send._Hands(hwnd)


def _click(hands: send._Hands, point: tuple[int, int]) -> None:
    try:
        hands.check_user()
        # arrive first, press after: a press in the same instant as the jump can miss the row
        win32api.SetCursorPos(point)
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 0, 0, 0)
        hands._done()
        hands.click(point)
    except send.Unclear as e:
        raise send.NotSent(str(e)) from e  # a click here sends nothing


def _activate(hwnd: int, hands: send._Hands) -> None:
    """Give WeChat the focus: a click into a window in the background only activates it and is lost."""
    if win32gui.GetForegroundWindow() == hwnd:
        return
    left, top, _, _ = win32gui.GetWindowRect(hwnd)
    # the empty strip above the chat's title: a single click there does nothing
    _click(hands, (left + wechat.pane_left(wechat.capture(hwnd)) + 120, top + TITLE_STRIP))
    for _ in range(10):
        time.sleep(0.2)
        if win32gui.GetForegroundWindow() == hwnd:
            time.sleep(0.6)  # longer than a double click, which would maximise
            return
    raise send.NotSent("WeChat did not take the focus")


_was_hidden: dict[int, bool] = {}  # windows we brought up: True = it was in the tray


def main_windows() -> list[int]:
    """The main window, also while it is in the tray or minimised. Login windows are small."""
    found = []

    def each(hwnd, _):
        if win32gui.GetClassName(hwnd) == wechat.WINDOW_CLASS and win32gui.GetWindowText(hwnd) in MAIN_TITLES:
            if watcher.process_name(win32process.GetWindowThreadProcessId(hwnd)[1]) == watcher.APP:
                left, _, right, _ = win32gui.GetWindowPlacement(hwnd)[4]  # its size when not minimised
                if right - left >= wechat.MAIN_MIN_WIDTH:
                    found.append(hwnd)
        return True

    win32gui.EnumWindows(each, None)
    return found


def _hotkey_registered() -> bool:
    """Someone holds Ctrl+Alt+W system-wide. If nobody does, the keys would land in the program in front."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if user32.RegisterHotKey(None, HOTKEY_PROBE, win32con.MOD_CONTROL | win32con.MOD_ALT, ord("W")):
        user32.UnregisterHotKey(None, HOTKEY_PROBE)
        return False
    return ctypes.get_last_error() == ALREADY_REGISTERED


def _press_hotkey(hands: send._Hands) -> None:
    if not _hotkey_registered():
        raise send.NotSent("WeChat's Ctrl+Alt+W hotkey is switched off")
    hands.check_user()
    keys = (win32con.VK_CONTROL, win32con.VK_MENU, ord("W"))
    try:
        for key in keys:
            win32api.keybd_event(key, 0, 0, 0)
    finally:
        for key in reversed(keys):
            win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
    try:
        hands._done()
    except send.Unclear as e:
        raise send.NotSent(str(e)) from e


def show() -> tuple[int, bool]:
    """(main window, whether we had to bring it up)."""
    hwnd = wechat.find_window()
    if hwnd:
        return hwnd, False
    if not send.away():
        raise send.NotSent("the user is not away")
    windows = main_windows()
    if not windows:
        raise send.NotSent("WeChat is not running or not logged in")
    if len(windows) > 1:
        raise send.NotSent("more than one WeChat main window")
    hwnd = windows[0]
    hidden = not win32gui.IsWindowVisible(hwnd)
    if hidden:
        # It toggles, so only ever pressed while the window is hidden. Once more if it stays hidden:
        # WeChat's idea of shown/hidden can be inverted, then the first press was "hide".
        hands = _hands(hwnd)
        for _ in range(2):
            _press_hotkey(hands)
            end = time.time() + HOTKEY_WITHIN
            while time.time() < end and not win32gui.IsWindowVisible(hwnd):
                time.sleep(0.2)
            if win32gui.IsWindowVisible(hwnd):
                break
    elif win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    _was_hidden[hwnd] = hidden
    end = time.time() + SHOW_WITHIN
    while time.time() < end:
        time.sleep(0.4)
        if wechat.find_window() == hwnd:
            time.sleep(1.5)  # it draws itself after it appears
            return hwnd, True
    put_away(hwnd)
    raise send.NotSent("the WeChat window did not come up")


def put_away(hwnd: int) -> None:
    """Only for a window we brought up: back to the tray or minimised, as it was."""
    if hwnd in _was_hidden and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
        if _was_hidden.pop(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)  # its X: WeChat itself goes to the tray
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


def _wheel(hwnd: int, hands: send._Hands, point: tuple[int, int], up: bool, notches: int = NOTCHES) -> None:
    hands.check_user()
    if not hands.owns(point):
        raise send.NotSent("another window covers WeChat")
    win32api.SetCursorPos(point)
    for _ in range(notches):
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120 if up else -120, 0)
    try:
        hands._done()
    except send.Unclear as e:
        raise send.NotSent(str(e)) from e
    time.sleep(1.0)


def open_chat(hwnd: int) -> bool:
    """The target's chat is open afterwards. False = it is not in the chat list."""
    img = wechat.capture(hwnd)
    if wechat.is_target_chat(img):
        return True
    hands = _hands(hwnd)
    with physical(), on_top(hwnd):
        _activate(hwnd, hands)
        left, top, _, _ = win32gui.GetWindowRect(hwnd)
        img = wechat.capture(hwnd)
        row = wechat.target_row(img)
        if not row:
            pane = wechat.pane_left(img)
            if pane < -wechat.LIST_NAME_X[0]:
                raise send.NotSent("WeChat's window has no chat list (login or another page?)")
            row = find_in_list(hwnd, hands, pane, (left + pane - 150, top + img.shape[0] // 2))
            if not row:
                return False
        _click(hands, (left + row[0], top + row[1]))
        for _ in range(10):
            time.sleep(0.4)
            if wechat.is_target_chat(wechat.capture(hwnd)):  # the strict check
                return True
    raise send.NotSent("clicked the chat, but its title is not the target")


def find_in_list(hwnd: int, hands: send._Hands, pane: int, point: tuple[int, int]) -> tuple[int, int] | None:
    """The target's line in the chat list: from the top, then down a bit at a time to the end.

    Other chats push it down (seen 2026-11-22 19:30: not on the first screen, so nothing was answered).
    Only the wheel and looking: no other chat is clicked. None = not in the whole list.
    """
    def look() -> np.ndarray:
        now = wechat.capture(hwnd)
        if wechat.pane_left(now) != pane:
            raise send.NotSent("WeChat's window changed while searching the chat list")
        return now[wechat.TITLE_BOTTOM:, :pane]

    def scroll(up: bool, notches: int) -> bool:
        """False once the wheel moves nothing any more."""
        before = look()
        _wheel(hwnd, hands, point, up=up, notches=notches)
        after = look()
        time.sleep(SETTLE)
        return moved(before, after, look())

    end = time.time() + LIST_WITHIN
    for _ in range(LIST_TOP_ROUNDS):  # to the top: where the newest chats are
        if not scroll(True, NOTCHES):
            break
    still = 0
    while True:
        row = wechat.target_row(wechat.capture(hwnd))
        if row or time.time() > end:
            break
        still = 0 if scroll(False, LIST_STEP) else still + 1
        if still >= STILL_ROUNDS:
            break
    if not row:
        with contextlib.suppress(send.NotSent):  # leave the list at the top, as it usually is
            for _ in range(LIST_TOP_ROUNDS):
                if not scroll(True, NOTCHES):
                    break
    return row


def to_newest(hwnd: int) -> None:
    """Scroll down until nothing moves any more: old cards must never count as new.

    Only down. If the bottom isn't reached, NotSent: then nothing on the screen counts as newest.
    """
    hands = _hands(hwnd)
    with physical(), on_top(hwnd):
        left, top, _, _ = win32gui.GetWindowRect(hwnd)
        img = wechat.capture(hwnd)
        if not wechat.is_target_chat(img):
            raise send.NotSent("the open chat is not the target")
        pane = wechat.pane_left(img)
        point = (left + (pane + img.shape[1]) // 2, top + img.shape[0] // 2)

        def look() -> np.ndarray:
            now = wechat.capture(hwnd)
            if not wechat.is_target_chat(now):
                raise send.NotSent("the chat changed while scrolling")
            return now[wechat.MESSAGES_TOP: now.shape[0] - wechat.INPUT_HEIGHT, pane: now.shape[1] - SCROLLBAR]

        end, still = time.time() + BOTTOM_WITHIN, 0
        before = look()
        while still < STILL_ROUNDS:
            if time.time() > end:
                raise send.NotSent("could not reach the newest message")
            _wheel(hwnd, hands, point, up=False)
            after = look()
            time.sleep(SETTLE)
            again = look()
            still = 0 if moved(before, after, again) else still + 1
            before = again


def moved(before: np.ndarray, after: np.ndarray, again: np.ndarray) -> bool:
    """Did the wheel move the messages? An animated sticker changes without it, so it doesn't count."""
    if not before.shape == after.shape == again.shape:
        return True
    by_itself = np.abs(after - again).max(axis=2) > wechat.INK
    changed = np.abs(before - again).max(axis=2) > wechat.INK
    animated = by_itself.any(axis=1)
    if animated.mean() > 0.6:
        return True  # nearly everything is still moving
    for a, b in wechat.runs(animated):  # the whole sticker, also rows equal in these two frames
        animated[max(0, a - 12): b + 12] = True
    return int((changed.any(axis=1) & ~animated).sum()) > MOVED_ROWS


def browsers() -> set[int]:
    found = set()

    def each(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == BROWSER_CLASS \
                and win32gui.GetWindowText(hwnd):
            if watcher.process_name(win32process.GetWindowThreadProcessId(hwnd)[1]) == BROWSER_APP:
                found.add(hwnd)
        return True

    win32gui.EnumWindows(each, None)
    return found


def _page_video(hwnd: int) -> str | None:
    """Video id of the page in this browser window."""
    return video.video_id(page_address(hwnd))


def page_address(hwnd: int) -> str:
    """Address of the page in this browser window (its top document, not the links in it)."""
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA

    uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    only_documents = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, DOCUMENT)
    found = uia.ElementFromHandle(hwnd).FindAll(UIA.TreeScope_Descendants, only_documents)
    for i in range(found.Length):
        address = str(found.GetElement(i).GetCurrentPropertyValue(VALUE) or "")
        if address.startswith("http"):
            return address  # the first document is the page itself
    return ""


def is_bilibili(address: str) -> bool:
    """Bilibili's own hosts, its short links (b23.tv) included. Not "has bilibili in it"."""
    return bool(_BILIBILI.match(address))


def browser_running() -> bool:
    """Is WeChat's built-in browser already running? If not, a click has to start it, which can take minutes."""
    return any(watcher.process_name(pid) == BROWSER_APP for pid in win32process.EnumProcesses())


def card_video(hwnd: int, key: str) -> str:
    """Click that card, read the address, close the window the click opened.

    The user's rule 2026-11-22: cards may be clicked, the address has to be bilibili. Anything
    else is closed as soon as its address shows, and never watched, summarised or answered.
    """
    if browsers():
        # closing it could take the user's own tabs along, leaving it would play into the recording
        raise send.NotSent("WeChat's built-in browser is already open")
    hands = _hands(hwnd)
    before = browsers()
    cold = not browser_running()
    try:
        with physical(), on_top(hwnd):
            _activate(hwnd, hands)
            left, top, _, _ = win32gui.GetWindowRect(hwnd)
            img = wechat.capture(hwnd)
            if not wechat.is_target_chat(img):
                raise send.NotSent("the open chat is not the target")
            cards = [c for c in wechat.incoming_bilibili_cards(img) if c.key == key]
            if not cards:
                raise send.NotSent("the card is not on the screen")
            # shared twice = the same key twice: the newest, as in wechat.own_messages_below
            _click(hands, (left + cards[-1].centre[0], top + cards[-1].centre[1]))
        end = time.time() + (PAGE_WITHIN_COLD if cold else PAGE_WITHIN)
        if cold:
            store.log("WeChat's built-in browser was not running: waiting longer for the page")
        bilibili_seen = False
        while time.time() < end:
            time.sleep(0.25)
            for window in browsers() - before:
                try:
                    address = page_address(window)
                except (OSError, comtypes.COMError):
                    continue  # still loading
                if not address:
                    continue
                if not is_bilibili(address):
                    raise video.CannotReply("the address is not bilibili, closed")
                found = video.video_id(address)  # None while a short link is still on its way
                if found:
                    return found
                bilibili_seen = True
        if bilibili_seen:  # it did open, just not a video: trying again won't change that
            raise video.CannotReply("the shared card did not open a Bilibili video page")
        # not a verdict on the card: slow to open (2026-11-23 12:07). Tried again later, up to MAX_TRIES times
        raise send.NotSent("the shared card did not open a page in time")
    finally:
        for window in browsers() - before:
            win32gui.PostMessage(window, win32con.WM_CLOSE, 0, 0)
        time.sleep(1.5)
