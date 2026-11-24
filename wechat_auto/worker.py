"""[deskpet] WeChat auto-reply, part 11: the worker. Two kinds of process:

  watch   always on while enabled: hears the message sound (volume to 0 at once if the user is
          away, untouched if not), waits until the user is away, sets it to 0, starts a job
  job     one look at WeChat and the replies that follow from it, in a process of its own (audio:
          see record.py), so a crash or a kill there never takes the watcher along

  python worker.py on        mark what is on screen as old, then switch on (needs the user away)
  python worker.py off       switch off; whatever runs stops before its next message
  python worker.py status
  python worker.py replies-off   mute only: the sound while away still mutes, WeChat is never opened
  python worker.py replies-on

The user's rule (2026-11-22): while he is writing in that chat himself, the pet does not take
over. A message of his under the card means exactly that, before starting and before each send.

What must hold: nothing is sent while switched off, nothing is answered twice, and a failure is
said to the user ("SAY: " lines, which the pet speaks and shows as a subtitle).
"""

import ctypes
import msvcrt
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent / "Open-LLM-VTuber"

import comtypes  # noqa: E402
import pywintypes  # noqa: E402
import win32pipe  # noqa: E402

import store  # noqa: E402
import watcher  # noqa: E402

# The watcher (message sound -> volume 0) is kept apart from the reply parts (the user, 2026-11-24:
# 「只需要检测微信提示音那个功能」): it needs store and watcher only. Replies happen in job processes,
# so a reply part that is broken or hangs while loading can never stop the mute.
WATCH_ONLY = __name__ == "__main__" and sys.argv[1:2] == ["watch"]
if WATCH_ONLY:
    listen = record = reply = screen = send = share = video = voice = wechat = None
else:
    import listen  # noqa: E402
    import record  # noqa: E402
    import reply  # noqa: E402
    import screen  # noqa: E402
    import send  # noqa: E402
    import share  # noqa: E402
    import video  # noqa: E402
    import voice  # noqa: E402
    import wechat  # noqa: E402

FINISHED, LATER, GAVE_UP = 0, 3, 4  # a job's exit codes
STOPPED = LATER     # ended because the pet went away: not a finished job
RECALLED = 1        # this many messages may be taken back without an old card passing for new
MAX_TRIES = 5       # failures that are not "the user came back"
RETRY_AFTER = 30.0  # seconds before another job after one that has to be tried again
PARENT_CHECK = 0.5  # seconds between looks whether the parent is still there
QUIET_FOR = 3.0     # the PC must be this long silent before a video is played to be listened to
BUSY_CHECK = 0.5   # seconds between looks at what else is playing
JOB_MUTEX = "deskpet-wechat-auto-job"  # the same name as in deskpet/quiet.py
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# what the user is told, by what the error says
REASONS = (
    ("STILL be recording", "微信可能还在录音，请马上看一眼微信"),
    ("unknown whether", "有一条不确定发出去没有，我没有补发"),
    ("no suitable video", "找不到够像的视频了"),
    ("not enough speech", "视频没什么人声，画面也没截到"),
    ("what the video is about", "听不出视频讲了什么"),
    ("must not be sent", "总结里有不适合自动发的内容"),
    ("longer than 20", "视频超过二十分钟"),
    ("did not start playing", "视频没播起来"),
    ("not bilibili", "那张卡片点开不是B站的网址，我关掉了，没回"),
    ("left bilibili", "页面不是B站的视频，我关掉了"),
    ("reach the newest", "聊天滚不到最新一条"),
    ("share button", "B站的转发按钮用不了，可能要登录或验证码"),
    ("did not open", "点开卡片后视频页面一直没打开，试了几次都不行"),
    ("next one began", "分不清视频在哪里结束"),
    ("draft", "输入框里有你没发完的内容"),
    ("not logged in", "微信没在运行，或者要重新登录"),
    ("hotkey", "微信的显示窗口快捷键 Ctrl+Alt+W 被关掉了"),
    ("did not come up", "微信窗口打不开"),
    ("main window", "开着不止一个微信，我不知道该用哪个"),
    ("built-in browser", "微信自带的浏览器开着，请关掉它"),
    ("other sound", "电脑一直有别的声音在放"),
    ("default device", "虚拟声卡被设成了默认设备"),
    ("cable", "微信没有从虚拟麦克风录音"),
    ("voice server", "我的语音服务没有回应"),
)


def why_text(error: BaseException) -> str:
    texts, e = [], error
    while e is not None:
        texts.append(str(e))
        e = e.__cause__
    everything = " | ".join(texts)
    return next((said for part, said in REASONS if part in everything), "中间出了点问题")


def say(text: str) -> None:
    store.log(f"told the user: {text}")
    print(f"SAY: {text}", flush=True)


def may_go_on() -> bool:
    return store.enabled() and store.replies_on() and send.away()


class Tools:
    """The slow things a job needs, made when first needed."""

    def __init__(self):
        self._gate = self._transcribe = None

    def _server_path(self) -> None:
        src = str(SERVER / "src")
        if src not in sys.path:
            sys.path.append(src)

    def gate(self):
        if self._gate is None:
            self._server_path()
            from open_llm_vtuber.deskpet import echo_gate

            echo_gate.start()
            end = time.time() + 10
            while not echo_gate._loop.ok:
                if time.time() > end:
                    raise send.NotSent("cannot listen to the speakers")
                time.sleep(0.2)
            self._gate = echo_gate
        return self._gate

    def watch_video(self, vid: str) -> tuple[str, str, list[bytes]]:
        gate = self.gate()
        time.sleep(QUIET_FOR)
        now = time.time()
        heard = gate._loop.window(now - QUIET_FOR, now - 0.2)
        if float((heard ** 2).mean() ** 0.5) > listen.SOUND:
            raise send.NotSent("other sound is playing and would be mixed into the video")
        return listen.listen(f"https://www.bilibili.com/video/{vid}/", gate._loop.window, self.transcribe,
                             away=may_go_on)

    def transcribe(self, audio):
        if self._transcribe is None:
            self._server_path()
            os.environ["HF_HUB_OFFLINE"] = "1"
            from open_llm_vtuber.asr.faster_whisper_asr import VoiceRecognition

            asr = VoiceRecognition(model_path="large-v3-turbo", download_root=str(SERVER / "models" / "whisper"),
                                   language="zh", device="cpu", compute_type="int8")
            self._transcribe = listen.transcriber(asr.model)
        return self._transcribe(audio)

    def send_voice(self, spoken: str, before_press) -> None:
        wav = voice.synthesize(spoken)  # can take minutes
        if not (store.enabled() and store.replies_on()):
            raise send.NotSent("switched off")
        record.send_wav(wav, before_press)

    def copy_link(self, url: str) -> str:
        return share.link(url, away=may_go_on)

    def send_link(self, text: str, before_click) -> None:
        if not (store.enabled() and store.replies_on()):
            raise send.NotSent("switched off")
        send.send(text, before_click)


class TookOver(Exception):
    """Not for the pet: he writes himself, or the card is off the screen. `seen` = which of the two."""

    def __init__(self, seen: bool):
        super().__init__("the user is writing himself" if seen else "the card left the screen")
        self.seen = seen


class Job:
    def __init__(self, handled: store.Handled, tools, ui=screen):
        self.handled, self.tools, self.ui = handled, tools, ui
        self.hwnd, self.brought_up = None, False
        self.taken: TookOver | None = None

    def chat(self) -> bool:
        hwnd, brought_up = self.ui.show()
        self.hwnd, self.brought_up = hwnd, self.brought_up or brought_up
        return self.ui.open_chat(hwnd)

    def check_not_taken(self, key: str) -> None:
        img = wechat.capture(self.hwnd)
        if not wechat.is_target_chat(img):
            raise send.NotSent("the open chat is not the target")
        # one that arrived meanwhile, noted now: otherwise what we send next would look like his answer to it
        for new in wechat.incoming_bilibili_cards(img):
            if (new.key not in self.handled.cards and wechat.own_messages_below(img, new.key) == 0
                    and self.arrived_since(img, new.key)):
                self.handled.start(new.key)
        below = wechat.own_messages_below(img, key)
        if below is None or below > self.handled.cards[key].get("ours", 0):
            self.taken = TookOver(seen=below is not None)
            raise self.taken

    def arrived_since(self, img, key: str) -> bool:
        """An unknown card is only new if fewer messages follow it than could be seen at an earlier look.

        A taller or wider window shows older cards: nobody noted those, but they have more below them.
        """
        below = wechat.messages_below(img, key)
        return below is not None and below < max(1, (self.handled.seen or 0) - RECALLED)

    def send_voice(self, key: str, spoken: str, mark) -> None:
        def last_look() -> None:
            self.check_not_taken(key)  # nothing has been clicked yet
            mark()

        self.tools.send_voice(spoken, last_look)
        self.handled.count_ours()

    def send_link(self, key: str, text: str, mark) -> None:
        self.check_not_taken(key)  # before pasting: afterwards it would be left in the input box
        self.tools.send_link(text, mark)
        self.handled.count_ours()

    def leave_to_him(self, key: str, why: TookOver) -> None:
        progress = reply.load(self.handled.replies, key)
        out = 0 if not progress else int(progress.voice_sent) + len(progress.links)
        self.handled.finish(key, store.YOURS, str(why))
        store.log(f"card {key}: left to the user after {out} messages: {why}")
        if out:
            say(f"贺那条我不接着回了，前面已经发出去{out}条。")
        elif not why.seen:  # could also be only his friend writing: then he should know
            say("贺那条视频已经被后面的消息顶上去了，我就不接手了。")

    def answer(self, key: str) -> None:
        card = self.handled.cards[key]
        vid = card.get("video")
        if not vid:
            if not self.chat():
                raise send.NotSent("the chat is not in the list")
            self.ui.to_newest(self.hwnd)
            self.check_not_taken(key)
            vid = self.ui.card_video(self.hwnd, key)
            if not self.handled.claim_video(key, vid):
                self.handled.finish(key, store.REPEAT, "same video as an earlier card")
                store.log(f"card {key}: a video already answered, left alone")
                return
        folder = self.handled.replies
        progress = reply.load(folder, key)
        if not progress:
            text, title, pictures = self.tools.watch_video(vid)
            progress = reply.begin(folder, key, f"https://www.bilibili.com/video/{vid}/", title, text, pictures)
            store.log(f"card {key}: watched, {len(text)} characters, {len(pictures)} pictures")
        if not self.chat():
            raise send.NotSent("the chat is not in the list")
        if not progress.sending:  # (an unknown send is reported by reply.run, whoever wrote since)
            self.ui.to_newest(self.hwnd)
            self.check_not_taken(key)
        reply.run(progress, folder, lambda spoken, mark: self.send_voice(key, spoken, mark),
                  lambda text, mark: self.send_link(key, text, mark), away=may_go_on,
                  copy_link=self.tools.copy_link)
        self.handled.finish(key, store.DONE)
        store.log(f"card {key}: voice and {len(progress.links)} links sent")
        say("贺发的视频我回好了，语音和一个相似的视频都发过去了。")

    def give_up(self, key: str, error: BaseException) -> None:
        progress = reply.load(self.handled.replies, key)
        out = 0 if not progress else int(progress.voice_sent) + len(progress.links)
        self.handled.finish(key, store.FAILED, str(error))
        store.log(f"card {key}: gave up after {out} messages: {error!r} / {error.__cause__!r}")
        say(f"贺那条视频我没回完：{why_text(error)}。已经发出去{out}条，剩下的你看一下微信。")

    def one(self, key: str) -> int:
        self.taken = None
        try:
            self.answer(key)
            return FINISHED
        except TookOver as e:
            self.leave_to_him(key, e)
            return FINISHED
        except (reply.Stuck, video.CannotReply, send.Unclear) as e:
            self.give_up(key, e)
            return FINISHED
        except Exception as e:  # includes send.NotSent, reply.Paused, listen.UserIsBack
            if self.taken:  # reached us wrapped in reply.Paused
                self.leave_to_him(key, self.taken)
                return FINISHED
            if may_go_on():  # not simply "he is back": count it
                card = self.handled.cards[key]
                card["tries"] = card.get("tries", 0) + 1
                self.handled.save()
                if card["tries"] >= MAX_TRIES:
                    self.give_up(key, e)
                    return FINISHED
            store.log(f"card {key}: later ({e!r})")
            return LATER

    def run(self) -> int:
        try:
            while may_go_on():
                waiting = self.handled.unfinished()
                if waiting:
                    if self.one(waiting[0]) == LATER:
                        return LATER
                    continue
                try:
                    if not self.chat():
                        store.log("looked: the chat is not in the list")
                        return FINISHED
                    self.ui.to_newest(self.hwnd)
                    img = wechat.capture(self.hwnd)
                    cards = wechat.incoming_bilibili_cards(img)
                except Exception as e:
                    store.log(f"could not look at WeChat: {e!r}")
                    if not may_go_on():
                        return LATER
                    print(f"look failed: {why_text(e)}", file=sys.stderr, flush=True)
                    return GAVE_UP
                # shared twice = the same key twice
                unknown = list(dict.fromkeys(c.key for c in cards if c.key not in self.handled.cards))
                new = [key for key in unknown if self.arrived_since(img, key)]
                too_far = [key for key in unknown if key not in new]
                if too_far:
                    self.handled.mark_old(too_far)
                    store.log(f"{len(too_far)} cards too far up to be new, left alone")
                    if not all(wechat.own_messages_below(img, key) for key in too_far):
                        say("贺那边有张视频卡片离最新消息太远，我分不清是不是新的，就没接手。")
                for key in new:  # all of them first, oldest first: a crash must not lose the later ones
                    self.handled.start(key)
                # only now, with every card on this screen noted
                self.handled.seen = max(self.handled.seen or 0, wechat.message_count(img))
                self.handled.save()
                if not new:
                    store.log("looked: nothing new to answer")
                    return FINISHED
                for key in new:
                    if wechat.own_messages_below(img, key):
                        self.leave_to_him(key, TookOver(seen=True))
            return LATER
        finally:
            if self.brought_up and self.hwnd:
                self.ui.put_away(self.hwnd)


class Watch:
    """The watcher's decisions, without the sound and process plumbing."""

    def __init__(self, state: Path, start_job):
        self.pending_file, self.start_job = state / "pending", start_job
        self.edge = watcher.SoundEdge()
        self.job, self.not_before, self.failures, self.heard_in_job = None, 0.0, 0, False
        self.resume = False

    def sound(self, level: float, now: float, in_front: bool, present: bool, away: bool = True) -> bool:
        """True = a message sound. Only one while he is away (away = may_mute) is looked into later.

        The user's rule (2026-11-23): only a sound while he does nothing mutes, and only that is answered.
        What rang while he was at the PC he saw himself: it is not kept for later.
        """
        if not self.edge.update(level, now):
            return False
        # WeChat in front is no notification while he uses it, or while a job is clicking in it
        if in_front and (present or self.job):
            return False
        if not away or not store.replies_on():
            return True  # mute only: nothing is kept to look into
        self.pending_file.parent.mkdir(parents=True, exist_ok=True)
        self.pending_file.write_text(time.strftime("%H:%M:%S"), encoding="utf-8")
        self.heard_in_job = bool(self.job)
        return True

    def tick(self, now: float, away) -> str | None:
        """Start or collect a job. Returns what to tell the user, if anything."""
        if self.job is not None:
            code = self.job.poll()
            if code is None:
                return None
            self.job = None
            if code == FINISHED:
                self.failures, self.resume = 0, False
                if not self.heard_in_job:
                    self.pending_file.unlink(missing_ok=True)
            else:
                self.not_before, self.resume = now + RETRY_AFTER, True
                if code != LATER:
                    self.failures += 1
                    if self.failures >= MAX_TRIES:
                        self.failures, self.resume = 0, False
                        self.pending_file.unlink(missing_ok=True)
                        return "微信来消息了，但我试了几次都看不了，你有空看一下微信。"
            return None
        if not store.replies_on():
            return None  # mute only: WeChat is never opened
        if (self.resume or self.pending_file.exists()) and now >= self.not_before and away():
            self.heard_in_job = False
            self.job = self.start_job()
        return None


def stop_with_parent() -> None:
    """The parent's end of stdin closes when it dies, also when it is killed.

    The pipe is only peeked at, never read while empty. While a read waits on it, whatever asks
    Windows about stdin waits too: loading scipy and every child process hung for good (2026-11-22).
    """
    fd = sys.stdin.fileno()
    if os.isatty(fd):
        return  # started by hand
    handle = msvcrt.get_osfhandle(fd)

    def wait():
        try:
            while True:
                waiting = win32pipe.PeekNamedPipe(handle, 0)[1]
                if waiting:
                    os.read(fd, waiting)  # it is there, so this returns at once
                time.sleep(PARENT_CHECK)
        except (OSError, pywintypes.error):
            pass  # a broken pipe is the parent gone
        os._exit(STOPPED)

    threading.Thread(target=wait, daemon=True).start()


def start_job() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-u", "-B", str(HERE / "worker.py"), "job", "--child"],
                            stdin=subprocess.PIPE, cwd=str(HERE), creationflags=NO_WINDOW)


def quiet_start() -> subprocess.Popen:
    # the volume is not touched here: only the message sound itself mutes (the user's rule, 2026-11-23)
    store.log("the user is away: looking")
    return start_job()


def watch() -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, "deskpet-wechat-auto-watch")
    if not mutex or ctypes.get_last_error() == 183:  # already exists
        store.log("a watcher is already running")
        return 0
    state = Watch(store.STATE, quiet_start)
    state.resume = bool(store.Handled().unfinished())
    store.log("watching")
    next_tick, next_error, next_busy = 0.0, 0.0, 0.0
    busy, playing = watcher.Busy(), ""
    while store.enabled():
        now = time.monotonic()
        try:
            if now >= next_busy:
                next_busy = now + BUSY_CHECK
                # while a job runs, the video it plays in WeChat's browser is ours, not the user's
                playing = busy.update(now, frozenset({"wechatappex.exe"}) if state.job else frozenset())
            level = watcher.app_level(watcher.APP)
            in_front = level > watcher.PEAK and watcher.foreground_app() == watcher.APP
            present = watcher.idle_seconds() < watcher.AWAY_SECONDS
            # a video, music or a meeting on: he is watching or listening, not away (the user, 2026-11-23)
            away = watcher.may_mute() and not playing
            if state.sound(level, now, in_front, present, away):
                if away:
                    watcher.set_volume(0.0)
                    store.log(f"message sound (level {level:.3f}): volume 0")
                elif playing:
                    store.log(f"message sound while {playing}: volume untouched, not looked into")
                else:
                    store.log("message sound, the user is here: volume untouched, not looked into")
            if now >= next_tick:
                next_tick = now + 1.0
                told = state.tick(now, lambda: watcher.may_take_screen() and not playing)
                if told:
                    say(told)
        except (OSError, comtypes.COMError) as e:  # speakers switched, a session just closed
            if now >= next_error:
                next_error = now + 60
                store.log(f"watch check failed, retrying: {e!r}")
            time.sleep(1)
        time.sleep(watcher.POLL)
    if state.job is not None:  # switched off: give it a moment to stop by itself, then make it
        try:
            state.job.wait(timeout=10)
        except subprocess.TimeoutExpired:
            state.job.stdin.close()
    store.log("switched off, watcher ends")
    return 0


def job() -> int:
    # held until this process ends, however it ends: the pet makes no sound meanwhile (deskpet/quiet.py),
    # what she said would be recorded with the video and sent
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    quiet = kernel32.CreateMutexW(None, False, JOB_MUTEX)
    if not quiet:
        store.log("could not tell the pet to be quiet: not looking")
        return LATER
    return Job(store.Handled(), Tools()).run()


def switch_on(keep_watching: bool = False) -> int:
    """keep_watching: only the replies are switched on again; the watcher (the mute) is not stopped for it."""
    print("等你松开键鼠 60 秒，再把屏幕上已有的视频都记成处理过……", flush=True)
    end = time.time() + 480
    while not watcher.may_take_screen():
        if time.time() > end:
            print("没有等到空闲，没有启用。")
            return 1
        time.sleep(1)
    if not keep_watching:
        store.set_enabled(False)
    hwnd, brought_up = screen.show()
    try:
        if not screen.open_chat(hwnd):
            print("会话列表里没找到贺，没有启用。")
            return 1
        screen.to_newest(hwnd)
        handled = store.Handled()
        img = wechat.capture(hwnd)
        keys = [c.key for c in wechat.incoming_bilibili_cards(img)]
        handled.seen = wechat.message_count(img)  # afresh: what came while it was off isn't known
        # also what was cut short while it was off: switching on never sends anything old
        for key in handled.unfinished():
            handled.finish(key, store.OLD, "switched on again")
        added = handled.mark_old(keys)
        (store.STATE / "pending").unlink(missing_ok=True)
        store.set_enabled(True)
        store.log(f"switched on, {added} cards marked old")
        print(f"已启用，{added} 条旧视频不会回。")
        return 0
    finally:
        if brought_up:
            screen.put_away(hwnd)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    what = sys.argv[1] if len(sys.argv) > 1 else "status"
    if what == "off":
        store.set_enabled(False)
        store.log("switched off")
        print("已关闭。")
        return 0
    if what == "status":
        waiting = len(store.Handled().unfinished())
        print(f"微信监听：{'开' if store.enabled() else '关'}，自动回复：{'开' if store.replies_on() else '关（只静音）'}，"
              f"没做完的 {waiting} 条。")
        return 0
    if what == "replies-off":
        store.set_replies(False)
        (store.STATE / "pending").unlink(missing_ok=True)
        store.log("replies off: mute only")
        print("自动回复已关，只留静音。")
        return 0
    if "--child" in sys.argv:
        stop_with_parent()
    comtypes.CoInitialize()
    if what == "replies-on":
        # what came while the replies were off is marked old first: it is never answered afterwards
        was_on = store.enabled()
        if switch_on(keep_watching=was_on) != 0:
            print("自动回复没有打开，静音不受影响。")
            return 1
        store.set_replies(True)
        store.log("replies on")
        print("自动回复已打开。")
        return 0
    if what == "on":
        return switch_on()
    if what == "watch":
        return watch()
    if what == "job":
        return job() if store.enabled() and store.replies_on() else FINISHED
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
