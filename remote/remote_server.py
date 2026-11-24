"""[deskpet] Phone remote for the desk pet.

A tiny always-on web server (Python standard library only) that the phone app talks to:
  - shows whether the pet is running, what she is doing, and recent conversation
  - sends typed commands to her, exactly as if typed into the pet on this PC
  - starts and stops the pet

Security: it only answers this PC and Tailscale addresses (100.64.0.0/10, fd7a:115c:a1e0::/48),
and every API call needs the token in remote/token.txt (created on first run).
Start it at login with remote/start_remote.vbs (see remote/README.md).
"""

import ipaddress
import json
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PORT = 12480
PET = "http://127.0.0.1:12393"
TOKEN_FILE = HERE / "token.txt"
LOG_FILE = HERE / "remote.log"
CLIENT_EXE = "open-llm-vtuber-electron.exe"
ALLOWED = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "::1/128", "100.64.0.0/10", "fd7a:115c:a1e0::/48")]
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def token() -> str:
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(18), encoding="utf-8")
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def log(msg: str) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def client_running() -> bool:
    if sys.platform != "win32":
        return False
    # /FO CSV: the default table cuts image names to 25 characters ("open-llm-vtuber-electron."),
    # so the full name never matched and the phone always said the pet was off
    # Bytes, decoded with the console code page: when nothing matches, tasklist prints a localized
    # message (GBK on this PC) and text=True under Python's UTF-8 mode failed to decode it -> None.
    raw = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {CLIENT_EXE}", "/NH", "/FO", "CSV"],
                         capture_output=True, creationflags=NO_WINDOW).stdout or b""
    out = raw.decode("mbcs", "replace")
    return f'"{CLIENT_EXE.lower()}"' in out.lower()


def pet_get(path: str):
    with urllib.request.urlopen(PET + path, timeout=4) as r:
        return json.loads(r.read().decode("utf-8"))


def pet_post(path: str, body: dict):
    req = urllib.request.Request(PET + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def status() -> dict:
    up = port_open(12393)
    info = {"server": up, "client": client_running(), "voice": port_open(9880), "ollama": port_open(11434)}
    try:  # the launcher writes "pct|text" while starting and "close" when done
        prog = (ROOT / "launcher" / "progress.txt").read_text(encoding="utf-16").strip()
        if prog and prog != "close" and "|" in prog and not info["client"]:
            info["starting"] = prog.split("|", 1)[1]
    except Exception:
        pass
    if up:
        try:
            info["pet"] = pet_get("/deskpet/remote/state")
        except Exception as e:
            info["pet_error"] = str(e)
    return info


def start_pet() -> str:
    if client_running():
        return "小克已经在运行了。"
    vbs = ROOT / "launcher" / "start_deskpet.vbs"
    subprocess.Popen(["wscript.exe", str(vbs)], creationflags=NO_WINDOW)
    log("start requested")
    return "正在启动，大约一两分钟。"


def stop_pet() -> str:
    log("stop requested")
    subprocess.run(["taskkill", "/IM", CLIENT_EXE, "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    for port in (12393, 9880):
        subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                        f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
                        "ForEach-Object { taskkill /PID $_.OwningProcess /T /F }"],
                       capture_output=True, creationflags=NO_WINDOW)
    return "已经关掉了，正在做的事也一起停了。"


class Handler(BaseHTTPRequestHandler):
    server_version = "deskpet-remote"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _allowed(self) -> bool:
        try:
            ip = ipaddress.ip_address(self.client_address[0].split("%")[0])
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            return any(ip in n for n in ALLOWED)
        except ValueError:
            return False

    def _send(self, code: int, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False).encode("utf-8")
                                                     if not isinstance(body, str) else body.encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Token", ""), token())

    def do_GET(self):
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        path = self.path.split("?")[0]
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/manifest.json": ("manifest.json", "application/manifest+json"),
                  "/icon.svg": ("icon.svg", "image/svg+xml")}
        if path in static:
            name, ctype = static[path]
            return self._send(200, (HERE / name).read_bytes(), ctype)
        if not self._authed():
            return self._send(401, {"error": "token"})
        if path == "/api/status":
            return self._send(200, status())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        if not self._authed():
            return self._send(401, {"error": "token"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send(400, {"ok": False, "message": "bad request"})
        if length < 0 or length > 64 * 1024:  # commands are short; don't read an unbounded body
            return self._send(413, {"ok": False, "message": "太长了"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        path = self.path.split("?")[0]
        try:
            if path == "/api/say":
                text = str(body.get("text", "")).strip()[:2000]
                if not text:
                    return self._send(400, {"ok": False, "message": "空的"})
                if not port_open(12393):
                    return self._send(200, {"ok": False, "message": "小克没在运行，先点开启。"})
                r = pet_post("/deskpet/remote/say", {"text": text})
                log(f"say: {text}")
                return self._send(200, {"ok": r.get("ok"), "message": "发过去了" if r.get("ok") else "小克的窗口没连上，等她完全启动再试。"})
            if path == "/api/start":
                return self._send(200, {"ok": True, "message": start_pet()})
            if path == "/api/stop":
                return self._send(200, {"ok": True, "message": stop_pet()})
        except Exception as e:
            return self._send(500, {"ok": False, "message": f"出错了：{e}"})
        self._send(404, {"error": "not found"})


class Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)  # accept IPv4 too
        super().server_bind()


if __name__ == "__main__":
    token()
    log(f"listening on port {PORT}")
    try:
        srv = Server(("::", PORT), Handler)
    except OSError:  # no IPv6 on this machine: IPv4 only
        Server.address_family = socket.AF_INET
        Server.server_bind = ThreadingHTTPServer.server_bind
        srv = Server(("0.0.0.0", PORT), Handler)
    srv.serve_forever()
