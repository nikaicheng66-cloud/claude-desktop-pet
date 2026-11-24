"""[deskpet] WeChat auto-reply, part 1: notice WeChat's message sound, and know when the user is away.

The user's rules (2026-11-22):
  - message sound while the user is away -> system volume to 0 at once, and it stays at 0.
    While he is at the PC the volume is left alone (changed by the user the same day)
  - only the private chat named exactly TARGET is ever answered; groups never
  - WeChat is only brought up while the user is away (no keyboard/mouse for AWAY_SECONDS)
  - replies are fully automatic once the whole feature is switched on

NOT wired into the pet yet: reading WeChat and replying still need calibrating on the real window.
Run by hand it only watches and prints; it changes the volume only with --mute.

  python watcher.py [--seconds 30] [--app weixin.exe] [--mute]

Detection reads each audio session's level (before the master volume), so it still hears the
next message while the volume is already 0. It reads levels only, never audio content.
"""

import argparse
import ctypes
import os
import time
from ctypes import HRESULT, POINTER, byref, c_float, c_int, c_void_p, cast
from ctypes.wintypes import BOOL, DWORD, UINT

import comtypes
from comtypes import COMMETHOD, GUID, IUnknown

TARGET = "贺"
APP = "weixin.exe"
AWAY_SECONDS = 60
POLL = 0.05    # seconds between level checks
PEAK = 0.002   # above this = making sound
QUIET = 1.5    # this long silent before another sound counts as a new message


def _m(name, *params):
    return COMMETHOD([], HRESULT, name, *params)


class Meter(IUnknown):
    _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
    _methods_ = [_m("GetPeakValue", (["out"], POINTER(c_float)))]


class Control(IUnknown):
    _iid_ = GUID("{bfb7ff88-7239-4fc9-8fa2-07c950be9c6d}")
    # only GetState and GetProcessId are called; the others just hold their place in the vtable
    _methods_ = ([_m("GetState", (["out"], POINTER(c_int)))] + [_m(f"unused{i}") for i in range(10)]
                 + [_m("GetProcessId", (["out"], POINTER(DWORD)))])


class Sessions(IUnknown):
    _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
    _methods_ = [_m("GetCount", (["out"], POINTER(c_int))),
                 _m("GetSession", (["in"], c_int), (["out"], POINTER(POINTER(IUnknown))))]


class Manager(IUnknown):
    _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
    _methods_ = [_m("unused0"), _m("unused1"),
                 _m("GetSessionEnumerator", (["out"], POINTER(POINTER(Sessions))))]


class Endpoint(IUnknown):
    _iid_ = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
    _methods_ = [_m(f"unused{i}") for i in range(4)] + [
        _m("SetMasterVolumeLevelScalar", (["in"], c_float), (["in"], c_void_p)),
        _m("unused4"),
        _m("GetMasterVolumeLevelScalar", (["out"], POINTER(c_float))),
    ]


class Device(IUnknown):
    _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
    _methods_ = [_m("Activate", (["in"], POINTER(GUID)), (["in"], DWORD), (["in"], c_void_p),
                    (["out"], POINTER(c_void_p)))]


class Devices(IUnknown):
    _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    _methods_ = [_m("unused0"),
                 _m("GetDefaultAudioEndpoint", (["in"], c_int), (["in"], c_int),
                    (["out"], POINTER(POINTER(Device))))]


def _speakers(interface, flow: int = 0, role: int = 1):
    """flow 0 = output (speakers), 1 = input (microphone); role 1 = multimedia, 2 = communications."""
    devices = comtypes.CoCreateInstance(GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), Devices,
                                        comtypes.CLSCTX_ALL)
    dev = devices.GetDefaultAudioEndpoint(flow, role)  # default device, looked up fresh each time
    return cast(dev.Activate(byref(interface._iid_), comtypes.CLSCTX_ALL, None), POINTER(interface))


def get_volume() -> float:
    return float(_speakers(Endpoint).GetMasterVolumeLevelScalar())


def set_volume(level: float) -> None:
    _speakers(Endpoint).SetMasterVolumeLevelScalar(level, None)


def process_name(pid: int) -> str:
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(260), DWORD(260)
        ok = k.QueryFullProcessImageNameW(h, 0, buf, byref(size))
        return os.path.basename(buf.value).lower() if ok else ""
    finally:
        k.CloseHandle(h)


def app_level(app: str) -> float:
    """Loudest current level among the app's audio sessions on the default speakers."""
    sessions = _speakers(Manager).GetSessionEnumerator()
    top = 0.0
    for i in range(sessions.GetCount()):
        s = sessions.GetSession(i)
        pid = s.QueryInterface(Control).GetProcessId()
        if pid and process_name(pid) == app:
            top = max(top, float(s.QueryInterface(Meter).GetPeakValue()))
    return top


def foreground_app() -> str:
    user32 = ctypes.windll.user32
    pid = DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), byref(pid))
    return process_name(pid.value)


def idle_seconds() -> float:
    class LastInput(ctypes.Structure):
        _fields_ = [("cbSize", UINT), ("dwTime", DWORD)]

    info = LastInput(ctypes.sizeof(LastInput), 0)
    if not ctypes.windll.user32.GetLastInputInfo(byref(info)):
        return 0.0  # unknown = treat as present
    # both are 32-bit millisecond ticks and wrap after 49.7 days
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def screen_locked() -> bool:
    user32 = ctypes.windll.user32
    desk = user32.OpenInputDesktop(0, BOOL(False), 0x0100)  # fails while the lock screen is up
    if not desk:
        return True
    user32.CloseDesktop(desk)
    return False


def fullscreen_busy() -> bool:
    """A full-screen game, video or presentation. A gamepad doesn't reset the idle time,
    so without this someone playing with one would look like he is away."""
    state = c_int()
    if ctypes.windll.shell32.SHQueryUserNotificationState(byref(state)) != 0:
        return True  # unknown = don't interrupt
    return state.value in (2, 3, 4)  # busy (full screen), Direct3D full screen, presentation


def may_take_screen() -> bool:
    """Away long enough, nothing full screen, and not locked (nothing can be clicked or read then)."""
    return idle_seconds() >= AWAY_SECONDS and not screen_locked() and not fullscreen_busy()


def may_mute() -> bool:
    """The volume is only taken while he is away. Locked is away too; full screen is not (gamepad, film)."""
    return screen_locked() or (idle_seconds() >= AWAY_SECONDS and not fullscreen_busy())


# The user (2026-11-23): 「在放视频或者音乐，会议的时候不准静音」.
# Sound from these is not a video, music or a meeting: WeChat itself (its message sound), the pet
# (her voice: the server and the window).
NOT_MEDIA = {"weixin.exe", "python.exe", "pythonw.exe", "open-llm-vtuber-electron.exe", "armouryaudioagent.exe"}
# The pet listens on the microphone all the time: that is no meeting
NOT_MEETING = {"python.exe", "pythonw.exe", "open-llm-vtuber-electron.exe", "armouryaudioagent.exe"}
MEETING_APPS = {"zoom.exe", "ms-teams.exe", "teams.exe", "wemeetapp.exe", "wemeet.exe", "voovmeetingapp.exe",
                "webex.exe", "ciscocollabhost.exe"}
ACTIVE = 1         # AudioSessionStateActive
MEDIA_RECENT = 20  # seconds: a pause in a video or between two songs is still playing


def _sessions(flow: int, role: int):
    """(process name, active, level) of each audio session on that default device."""
    sessions = _speakers(Manager, flow, role).GetSessionEnumerator()
    for i in range(sessions.GetCount()):
        s = sessions.GetSession(i)
        control = s.QueryInterface(Control)
        pid = control.GetProcessId()
        if not pid:
            continue  # Windows' own sounds
        yield process_name(pid), control.GetState() == ACTIVE, float(s.QueryInterface(Meter).GetPeakValue())


def busy_now(also_not: frozenset = frozenset()) -> str:
    """What is playing or in a meeting right now ('' = nothing). Levels only, never audio content.

    Media: another program makes sound on the speakers. Meeting: someone else holds the microphone
    open (a call or meeting, also while nobody talks), or a meeting app has its sound open.
    also_not: programs whose sound is ours this time (the job plays the video in wechatappex).
    """
    skip = NOT_MEDIA | also_not
    for role in (1, 2):
        for name, active, level in _sessions(0, role):
            if name in MEETING_APPS and active:
                return f"meeting: {name}"
            if name not in skip and level > PEAK:
                return f"playing: {name}"
    for role in (1, 2):
        try:
            mics = list(_sessions(1, role))
        except (OSError, comtypes.COMError):
            continue  # no microphone
        for name, active, _ in mics:
            if active and name not in NOT_MEETING | also_not:
                return f"meeting: {name} uses the microphone"
    return ""


class Busy:
    """Remembers playing for MEDIA_RECENT seconds, so a quiet moment in a film doesn't count as stopped."""

    def __init__(self, check=busy_now):
        self.check, self.what, self.until = check, "", float("-inf")

    def update(self, now: float, also_not: frozenset = frozenset()) -> str:
        what = self.check(also_not)
        if what:
            self.what = what
            self.until = now + (0 if what.startswith("meeting") else MEDIA_RECENT)
        return what or (self.what if now < self.until else "")


class SoundEdge:
    """Turns a stream of levels into 'a new sound started' events."""

    def __init__(self):
        self.last_sound = float("-inf")

    def update(self, level: float, now: float) -> bool:
        if level <= PEAK:
            return False
        started = now - self.last_sound >= QUIET
        self.last_sound = now
        return started


def watch(app: str = APP, mute: bool = False, seconds: float | None = None, on_sound=None) -> int:
    comtypes.CoInitialize()
    edge, count, began = SoundEdge(), 0, time.monotonic()
    while seconds is None or time.monotonic() - began < seconds:
        try:
            # WeChat in front = he is using it (a voice message, a video): not a notification
            if edge.update(app_level(app), time.monotonic()) and foreground_app() != app:
                if mute and may_mute():
                    set_volume(0.0)
                count += 1
                if on_sound:
                    on_sound()
        except (OSError, comtypes.COMError) as e:  # speakers switched, or a session just closed
            print(f"audio check failed, retrying: {e}", flush=True)
            time.sleep(1)
        time.sleep(POLL)
    return count


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float)
    p.add_argument("--app", default=APP)
    p.add_argument("--mute", action="store_true")
    a = p.parse_args()
    n = watch(a.app.lower(), a.mute, a.seconds,
              lambda: print(f"{time.strftime('%H:%M:%S')} sound; may take the screen now: {may_take_screen()}", flush=True))
    print(f"{n} sound(s)")
