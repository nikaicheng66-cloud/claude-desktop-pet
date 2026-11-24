"""[deskpet] WeChat auto-reply, part 12: a video's link, from Bilibili's own share arrow.

The user's rule (2026-11-22): click the arrow under the video and paste to the contact what that
puts on the clipboard. Measured: the arrow itself copies "【title】 address", the same text as its
menu's 微信 and 获取视频分享链接. So only the arrow is clicked. The menu also holds items that
publish under the user's account (动态 etc.): nothing in it is ever clicked.

What was copied is only used if it is fresh and is this very video. Nothing here sends.
"""

import re
import time

import comtypes
import comtypes.client
import win32api
import win32clipboard
import win32con

import listen
import screen
import send
import video

ARROW = "share-btn-outer"
ARROW_WITHIN = 15.0
COPY_WITHIN = 3.0
MAX_TEXT = 300
_SHARED = re.compile(r"(?:【(?P<title>[^\r\n]*)】[ \t]*)?(?P<url>https://www\.bilibili\.com/video/BV[0-9A-Za-z]{10}/?(?:\?[0-9A-Za-z_=&.\-]*)?)")
_ADDRESS = re.compile(r"[0-9a-z-]\.[a-z]{2,}", re.I)  # WeChat would make such a word clickable
_BLOCKED = re.compile(r"^(?:验证码|安全验证|登录)")


class Unusable(Exception):
    """This one video can't be shared: take another."""


def checked(copied: str, vid: str) -> str:
    """The copied text, if it may go out as it is."""
    text = copied.strip()
    m = _SHARED.fullmatch(text)
    if not m or len(text) > MAX_TEXT:
        raise Unusable("the share button copied something unexpected")
    if video.video_id(m["url"]) != vid:
        raise Unusable("the share button copied another video")
    title = m["title"] or ""
    if video._UNSAFE.search(title) or video._AD.search(title) or _ADDRESS.search(title):
        raise Unusable("the copied title must not be sent")  # a stranger wrote it and nobody reads it first
    return text


def _uia():
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA

    return UIA, comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)


def _find_arrow(hwnd: int, check) -> tuple[int, int, int, int]:
    """Its box, once it stopped moving."""
    UIA, uia = _uia()
    wanted = uia.CreatePropertyCondition(UIA.UIA_AutomationIdPropertyId, ARROW)
    last, seen = None, False
    end = time.time() + ARROW_WITHIN
    while time.time() < end:
        time.sleep(1.0)
        check()
        try:
            root = uia.ElementFromHandle(hwnd)
            arrow = root.FindFirst(UIA.TreeScope_Descendants, wanted)
            if not arrow:
                continue
            seen = True
            r = arrow.CurrentBoundingRectangle
            if arrow.CurrentIsOffscreen or r.right <= r.left:
                continue
            box = (r.left, r.top, r.right, r.bottom)
        except (OSError, comtypes.COMError):
            continue  # still loading
        if box == last:
            return box
        last = box
    if seen:
        raise video.CannotReply("the share button is not on the screen")
    if _BLOCKED.search(listen.title_of(hwnd)):
        raise video.CannotReply("the video page did not open (login or captcha)")
    raise Unusable("the page has no share button")  # removed or not a normal video


def _is_arrow(point: tuple[int, int]) -> bool:
    """What a click there would hit. Next to the arrow are 收藏 and 投币, above it the menu."""
    UIA, uia = _uia()
    try:
        element = uia.ElementFromPoint(UIA.tagPOINT(*point))
        for _ in range(6):
            if not element:
                break
            if element.CurrentAutomationId == ARROW:
                return True
            element = uia.RawViewWalker.GetParentElement(element)
    except (OSError, comtypes.COMError):
        pass
    return False


def _press(hwnd: int, hands: send._Hands, box: tuple[int, int, int, int]) -> None:
    left, top, _, bottom = box
    point = (left + (bottom - top) // 2, (top + bottom) // 2)  # the icon
    hands.check_user()
    if not hands.owns(point):
        raise send.NotSent("another window covers the video page")
    win32api.SetCursorPos(point)
    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 0, 0, 0)
    hands._done()
    time.sleep(0.8)  # the menu opens on hovering
    if not _is_arrow(point):
        raise video.CannotReply("the share button is covered (login or captcha)")
    screen._click(hands, point)


def _copy(hwnd: int, hands: send._Hands, box: tuple[int, int, int, int], vid: str) -> str:
    saved = send._save_clipboard()
    before = win32clipboard.GetClipboardSequenceNumber()
    try:
        _press(hwnd, hands, box)
        end = time.time() + COPY_WITHIN
        while time.time() < end:
            time.sleep(0.2)
            hands.check_user()  # what he copies himself is not for sending
            if win32clipboard.GetClipboardSequenceNumber() != before:
                time.sleep(0.3)
                hands.check_user()
                return send._get_text()
        raise video.CannotReply("the share button copied nothing")
    finally:
        try:
            # put back only over our own copy, never over something the user copied meanwhile
            if win32clipboard.GetClipboardSequenceNumber() != before and vid in send._get_text():
                send._set_clipboard(saved)
        except Exception as e:
            print(f"[deskpet] could not put the clipboard back: {e}", flush=True)


def link(url: str, away=send.away) -> str:
    """Open the video in a window of its own, click the arrow, return what it copied, close it."""
    vid = video.video_id(url) or ""
    if not vid.startswith("BV"):
        raise Unusable("not a BV link")  # an av address changes on loading and could not be compared
    if not away():
        raise send.NotSent("the user is not away")
    with screen.physical():
        hands = send._Hands(0)  # from here on any input but ours stops it
        with listen.Page(vid, hands.check_user) as page:
            hwnd = hands.hwnd = page.hwnd
            box = _find_arrow(hwnd, hands.check_user)
            if screen._page_video(hwnd) != vid:
                raise Unusable("the page shows another video")  # redirected, or autoplay moved on
            with screen.on_top(hwnd):
                if not away():
                    raise send.NotSent("the user is not away")
                return checked(_copy(hwnd, hands, box, vid), vid)
