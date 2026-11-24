"""[deskpet] WeChat auto-reply, part 8: a real voice message. Click WeChat's voice button (it starts
recording), play her voice into the virtual cable that WeChat records from, click the arrow (send).

What must never happen is the room's microphone, or other programs' sound, going to someone:
  - the cable must not be a default device (other programs' sound would be in the recording)
  - the mixer's per-app choice does not cover the 'communications' role, so it is not trusted:
    once it records, the microphone WeChat really records from must be the cable and
    nothing else, before her voice starts and for as long as it plays
  - anything wrong while it records: cancel (Esc, else the x) and make sure it stopped, then Unclear.

From the first click on the voice button nothing is retried, because a message may be out.

Run this in a process of its own, not inside the pet's server: a second PortAudio user there
would stop the echo gate from re-reading the device list when the speakers change.
"""

import ctypes
import io
import threading
import time
import winreg
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p, cast
from ctypes.wintypes import DWORD

import comtypes
import numpy as np
import win32api
import win32con
import win32gui
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

import send
import voice
import watcher
import wechat

VOICE_POINT = (129, 52)  # from the window's right and bottom edges
LEAD = 0.4               # silence between "it records from the cable" and her first word
TAIL = 0.5
OPEN_WITHIN = 2.0        # WeChat must start recording this soon after the press
LIMIT = 58.0             # whole recording; WeChat cuts at 60 s
RECORDER_SEND = (62, 57) # the arrow of the recorder, which replaces the voice button while recording
RECORDER_X = (314, 57)   # its cancel button
CHANGED = 500            # pixels of our own green bubbles that differ once a new one is there
BUFFER = 0.2             # seconds of playback buffer
PLAY_SLACK = 3.0         # playing may take this much longer than the sound
CABLE_IN, CABLE_OUT ="CABLE Input", "CABLE Output"
ACTIVE = 1


def _m(name, *params):
    return COMMETHOD([], HRESULT, name, *params)


class _Device(IUnknown):
    _iid_ = watcher.Device._iid_
    _methods_ = [_m("Activate", (["in"], POINTER(GUID)), (["in"], DWORD), (["in"], c_void_p),
                    (["out"], POINTER(c_void_p))),
                 _m("unused"),
                 _m("GetId", (["out"], POINTER(c_void_p)))]


class _Collection(IUnknown):
    _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
    _methods_ = [_m("GetCount", (["out"], POINTER(c_uint))),
                 _m("Item", (["in"], c_uint), (["out"], POINTER(POINTER(_Device))))]


class _Enumerator(IUnknown):
    _iid_ = watcher.Devices._iid_
    _methods_ = [_m("EnumAudioEndpoints", (["in"], c_uint), (["in"], DWORD), (["out"], POINTER(POINTER(_Collection)))),
                 _m("GetDefaultAudioEndpoint", (["in"], c_int), (["in"], c_int), (["out"], POINTER(POINTER(_Device))))]


class _Control(IUnknown):
    _iid_ = watcher.Control._iid_
    _methods_ = [_m("GetState", (["out"], POINTER(c_int)))] + [_m(f"unused{i}") for i in range(10)] + [
        _m("GetProcessId", (["out"], POINTER(DWORD)))]


def _enumerator():
    return comtypes.CoCreateInstance(GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), _Enumerator,
                                     comtypes.CLSCTX_ALL)


def _name(device, kind: str) -> str:
    raw = device.GetId()
    try:
        guid = ctypes.wstring_at(raw).split("}.")[-1]
    finally:
        free = ctypes.WinDLL("ole32").CoTaskMemFree
        free.argtypes = [c_void_p]
        free(raw)
    key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\{kind}\{guid}\Properties"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
        return str(winreg.QueryValueEx(k, "{a45c254e-df1c-4efd-8020-67d146a850e0},2")[0])


def cable_is_default() -> bool:
    devices = _enumerator()
    for flow, kind in ((0, "Render"), (1, "Capture")):
        for role in range(3):  # console, multimedia, communications
            if "CABLE" in _name(devices.GetDefaultAudioEndpoint(flow, role), kind).upper():
                return True
    return False


def recording_from(app: str = watcher.APP) -> dict[str, float]:
    """Microphones the app is recording from right now, with that microphone's level."""
    mics = _enumerator().EnumAudioEndpoints(1, 1)  # capture, active
    found = {}
    for i in range(mics.GetCount()):
        device = mics.Item(i)
        manager = cast(device.Activate(byref(watcher.Manager._iid_), 23, None), POINTER(watcher.Manager))
        sessions = manager.GetSessionEnumerator()
        for j in range(sessions.GetCount()):
            control = sessions.GetSession(j).QueryInterface(_Control)
            if control.GetState() != ACTIVE:
                continue
            pid = control.GetProcessId()
            if pid and watcher.process_name(pid) == app:
                meter = cast(device.Activate(byref(watcher.Meter._iid_), 23, None), POINTER(watcher.Meter))
                found[_name(device, "Capture")] = float(c_float(meter.GetPeakValue()).value)
    return found


class _Player:
    """Her voice into CABLE Input, nowhere else."""

    def __init__(self, wav: bytes):
        import pyaudiowpatch as pyaudio
        from scipy.io import wavfile
        from scipy.signal import resample_poly

        self.pa = pyaudio.PyAudio()
        try:
            api = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            found = [d for d in (self.pa.get_device_info_by_index(i) for i in range(self.pa.get_device_count()))
                     if d["hostApi"] == api["index"] and d["maxOutputChannels"] and d["name"].startswith(CABLE_IN)]
            if len(found) != 1:
                raise send.NotSent("the virtual cable was not found")
            self.rate, self.channels = int(found[0]["defaultSampleRate"]), int(found[0]["maxOutputChannels"])
            sr, samples = wavfile.read(io.BytesIO(wav))
            if samples.dtype != np.int16:
                raise send.NotSent("unexpected sound format")
            mono = samples.astype(np.float32) / 32768
            if mono.ndim > 1:
                mono = mono.mean(axis=1)
            samples = resample_poly(mono, self.rate, sr).astype(np.float32)
            self.length = len(samples) / self.rate
            data = np.repeat(samples, self.channels).tobytes()
            width, at = 4 * self.channels, 0
            self.done, self.halt = threading.Event(), threading.Event()

            def feed(_, frames, info, status):
                nonlocal at
                size = frames * width
                part = b"" if self.halt.is_set() else data[at:at + size]
                at += len(part)
                if at >= len(data):
                    self.done.set()
                return part + bytes(size - len(part)), pyaudio.paContinue

            # PortAudio pulls from a 200 ms buffer. Writing 50 ms pieces from this thread into the
            # default 22 ms buffer stuttered: 15-18 breaks in 10 s, 120 with the PC busy.
            self.stream = self.pa.open(format=pyaudio.paFloat32, channels=self.channels, rate=self.rate,
                                       output=True, output_device_index=found[0]["index"], start=False,
                                       frames_per_buffer=int(self.rate * BUFFER), stream_callback=feed)
        except BaseException:
            self.pa.terminate()
            raise

    def play(self, check) -> None:
        """Returns once her last word is in the cable; silent within a buffer if check() objects."""
        try:
            check()
            self.stream.start_stream()
            give_up = time.monotonic() + self.length + PLAY_SLACK
            while not self.done.wait(0.05):
                check()
                if time.monotonic() > give_up:
                    raise send.Unclear("the virtual cable stopped taking sound")
            # handed over is not played yet: what is in the buffer still has to come out
            left = time.monotonic() + self.stream.get_output_latency() + BUFFER
            while time.monotonic() < left:
                check()
                time.sleep(0.05)
        except BaseException:
            self.halt.set()  # at once: cancelling takes a second or two and must not hear her go on
            raise

    def close(self) -> None:
        try:
            self.stream.close()
        finally:
            self.pa.terminate()


def _click(point: tuple[int, int]) -> None:
    win32api.SetCursorPos(point)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def recorder_shown(img: np.ndarray) -> bool:
    """The green round arrow is where 发送 is otherwise grey."""
    h, w = img.shape[:2]
    x, y = w - RECORDER_SEND[0], h - RECORDER_SEND[1]
    r, g, _ = np.moveaxis(img[y - 14:y + 14, x - 14:x + 14], 2, 0)
    round_green = ((g - r) > 80).mean()
    left = img[y - 4:y + 4, x - 120:x - 100]  # the recorder's grey bar, left of the arrow
    return bool(round_green > 0.4 and (np.median(left.reshape(-1, 3), axis=0) < 244).all())


def _own_bubbles(img: np.ndarray) -> np.ndarray:
    """Where our green bubbles are. Hover marks and timestamps don't change this, a new message does."""
    area = img[wechat.MESSAGES_TOP: img.shape[0] - wechat.INPUT_HEIGHT, wechat.pane_left(img):]
    r, g, b = np.moveaxis(area, 2, 0)
    return (g - r > 25) & (g - b > 10) & (g > 150)


def _cancel(hwnd: int, hands, x_button: tuple[int, int]) -> bool:
    """Stop a recording without sending it. True once WeChat no longer records."""
    def stopped(within: float) -> bool:
        end = time.time() + within
        while True:
            if not recording_from():
                return True
            if time.time() >= end:
                return False
            time.sleep(0.1)

    try:
        if win32gui.GetForegroundWindow() == hwnd:  # never Esc into whatever he switched to
            win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
            win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
            if stopped(1.0):
                return True
        if recorder_shown(wechat.capture(hwnd)):
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            try:
                if hands.owns(x_button):
                    _click(x_button)
            finally:
                win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        return stopped(1.5)
    except Exception as e:
        print(f"[deskpet] cancelling the recording failed: {e}", flush=True)
        return False


def send_wav(wav: bytes, before_press=lambda: None, right_chat=wechat.is_target_chat) -> float:
    """Send `wav` as a voice message to the open chat, which must pass right_chat(image).

    Returns the loudest level WeChat's microphone saw. NotSent = the voice button was never clicked.
    """
    if not send.away():
        raise send.NotSent("the user is not away")
    if voice.seconds(wav) + OPEN_WITHIN + LEAD + TAIL > LIMIT:
        raise send.NotSent("too long for one voice message")
    if cable_is_default():
        raise send.NotSent("the virtual cable is a default device: other programs' sound would be recorded")
    if recording_from():
        raise send.NotSent("WeChat is already using a microphone (a call?)")
    hwnd = wechat.find_window()
    if not hwnd:
        raise send.NotSent("the WeChat window is not visible")
    img = wechat.capture(hwnd)
    if not right_chat(img):
        raise send.NotSent("the open chat is not the right one")
    if not wechat.input_is_empty(img):
        raise send.NotSent("there is a draft in the input box")

    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [c_void_p]
    scaling = user32.SetThreadDpiAwarenessContext(c_void_p(-4))  # physical pixels
    cursor = win32api.GetCursorPos()
    flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    raised, player = False, None
    try:
        player = _Player(wav)  # everything that can fail slowly, before the click
        left, _, right, bottom = rect = win32gui.GetWindowRect(hwnd)
        box = (left + wechat.pane_left(img) + send.INPUT_POINT[0], bottom - send.INPUT_POINT[1])
        button = (right - VOICE_POINT[0], bottom - VOICE_POINT[1])
        arrow = (right - RECORDER_SEND[0], bottom - RECORDER_SEND[1])
        x_button = (right - RECORDER_X[0], bottom - RECORDER_X[1])
        hands = send._Hands(hwnd)
        if not (hands.owns(box) and hands.owns(button)):
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
            raised = True
            time.sleep(0.4)
            if not hands.owns(button):
                raise send.NotSent("another window covers WeChat")
        try:
            hands.click(box)  # gives WeChat the focus, which Esc needs
        except send.Unclear as e:
            raise send.NotSent(str(e)) from e  # only the input box was clicked
        time.sleep(0.5)
        if win32gui.GetForegroundWindow() != hwnd:
            raise send.NotSent("WeChat did not take the focus")
        shown = wechat.capture(hwnd)
        if not right_chat(shown) or win32gui.GetWindowRect(hwnd) != rect:
            raise send.NotSent("the chat or the window changed")
        if not wechat.input_is_empty(shown):
            raise send.NotSent("there is a draft in the input box")
        bubbles = _own_bubbles(shown)
        hands.check_user()
        if not hands.owns(button):
            raise send.NotSent("another window covers WeChat")
        before_press()

        recording, peak, checked = False, 0.0, 0.0
        try:
            recording = True
            _click(button)
            hands._done()

            opened = time.time()
            while time.time() - opened < OPEN_WITHIN:
                hands.check_user()
                if recording_from():
                    break
                time.sleep(0.05)

            def check() -> None:
                nonlocal peak, checked
                hands.check_user()
                if time.time() - checked < 0.2:
                    return
                checked = time.time()
                now = recording_from()
                if len(now) != 1 or not next(iter(now)).startswith(CABLE_OUT):
                    raise send.Unclear(f"WeChat records from {list(now) or 'nothing'}, not from the cable")
                peak = max(peak, *now.values())

            check()
            time.sleep(LEAD)
            player.play(check)
            time.sleep(TAIL)
            check()
            if peak <= watcher.PEAK:
                raise send.Unclear("no sound reached WeChat's microphone")
            now_shown = wechat.capture(hwnd)
            if not recorder_shown(now_shown) or not right_chat(now_shown) or win32gui.GetWindowRect(hwnd) != rect:
                raise send.Unclear("the recorder or the chat changed")
            if win32gui.GetForegroundWindow() != hwnd or not hands.owns(arrow):
                raise send.Unclear("WeChat is not in front any more")
            hands.check_user()
            recording = False  # from here on it may be sent: don't cancel, only confirm
            _click(arrow)  # the one click that sends
            hands._done()
        except BaseException as e:
            stopped = True
            if recording:
                stopped = _cancel(hwnd, hands, x_button)
                try:
                    hands._done()
                except send.Unclear:
                    pass
            if not stopped:
                raise send.Unclear(f"WeChat may STILL be recording, tell the user at once: {e}") from e
            if isinstance(e, send.Unclear):
                raise
            # NotSent would mean "safe to try again", which is no longer true once clicked
            raise send.Unclear(f"stopped while recording: {e}") from e

        for _ in range(10):
            time.sleep(0.5)
            after = wechat.capture(hwnd)
            if recording_from() or recorder_shown(after) or not right_chat(after):
                continue
            now_bubbles = _own_bubbles(after)
            if now_bubbles.shape == bubbles.shape and int((now_bubbles ^ bubbles).sum()) > CHANGED:
                return peak
        if recording_from():
            stopped = _cancel(hwnd, hands, x_button)
            raise send.Unclear("the send click did nothing; "
                               + ("cancelled" if stopped else "WeChat may STILL be recording"))
        raise send.Unclear("clicked send, but no new message appeared")
    finally:
        for undo in (
            lambda: player and player.close(),
            lambda: raised and win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags),
            lambda: win32api.SetCursorPos(cursor),
        ):
            try:
                undo()
            except Exception as e:
                print(f"[deskpet] clean-up after recording failed: {e}", flush=True)
        user32.SetThreadDpiAwarenessContext(scaling)


def send_voice(spoken: str, before_press=lambda: None) -> None:
    """reply.run's send_voice: always the target's chat, never another."""
    send_wav(voice.synthesize(spoken), before_press)
