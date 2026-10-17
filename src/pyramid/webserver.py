"""pyramid web: the web page served on this computer, with the OAuth clients
saved in the desktop app.

The server listens on 127.0.0.1 only. The browser is opened on a private
temporary file that redirects with a one-time key (so the key never shows in
a process list); the key is traded for an HttpOnly, SameSite=Strict cookie
named after the port. Every /local/ call needs that cookie, and the Host
header must be this server, so other sites and DNS rebinding cannot reach the
proxy. Static files come from a fixed list. The proxy forwards GETs to
/api/v2/ only and adds the token itself: secrets never reach the page.
"""

from __future__ import annotations

import html
import json
import logging
import mimetypes
import os
import re
import secrets
import tempfile
import threading
import urllib.parse
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from . import __version__
from .client import ApiError, GenesysClient
from .config import Store

log = logging.getLogger(__name__)
COOKIE = "pyramid_session"
SAFE_API_PATH = re.compile(r"^/api/v2/[A-Za-z0-9_\-/.]*$")


def cookie_name(port: int) -> str:
    """Browsers share cookies between ports of one host: name it after the port."""
    return f"{COOKIE}_{port}"


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, store: Store):
        super().__init__(addr, Handler)
        self.store = store
        self.key = secrets.token_urlsafe(32)          # the cookie value
        self.url_key: str | None = secrets.token_urlsafe(32)  # one-time, in the address opened
        self.clients: dict[str, tuple[tuple, GenesysClient]] = {}
        self.lock = threading.Lock()

    @property
    def cookie(self) -> str:
        return cookie_name(self.server_address[1])

    def take_url_key(self, offered: str) -> bool:
        """The address with the key works once; then only the cookie does."""
        with self.lock:
            if self.url_key and secrets.compare_digest(offered, self.url_key):
                self.url_key = None
                return True
            return False

    def info(self) -> dict:
        with self.lock:
            self.store.reload_if_changed()
            return {"clients": [{"name": c.name, "region": c.region} for c in self.store.clients()],
                    "last": self.store.get("last_client")}

    def client(self, name: str) -> GenesysClient | None:
        with self.lock:
            self.store.reload_if_changed()
            c = self.store.client(name)
            if not c:
                return None
            proxy = self.store.proxy()
            key = (c.region, c.client_id, c.client_secret, proxy)  # an edited secret or proxy takes effect
            cached = self.clients.get(name)
            if cached is None or cached[0] != key:
                cached = (key, GenesysClient(c.region, c.client_id, c.client_secret, proxy=proxy))
                self.clients[name] = cached
            return cached[1]


def _static_files() -> dict[str, object]:
    """Every file the page may load, by URL name: nothing else is ever read."""
    web = resources.files("pyramid").joinpath("web")
    files = {f.name: f for f in web.iterdir() if f.is_file() and not f.name.startswith(".")}
    files["catalog.json"] = resources.files("pyramid").joinpath("catalog.json")
    return files


STATIC = _static_files()


def _web_file(path: str) -> bytes | None:
    name = "index.html" if path in ("", "/") else path[1:] if path.startswith("/") else path
    node = STATIC.get(name)
    return node.read_bytes() if node is not None else None


class Handler(BaseHTTPRequestHandler):
    server: LocalServer
    server_version = f"Pyramid/{__version__}"

    def log_message(self, fmt, *args):
        log.debug("web: " + fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj, extra=None):
        self._send(code, json.dumps(obj).encode(), "application/json", extra)

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _authed(self) -> bool:
        try:
            c = SimpleCookie(self.headers.get("Cookie", ""))
        except Exception:  # a malformed Cookie header
            return False
        name = self.server.cookie
        return name in c and secrets.compare_digest(c[name].value, self.server.key)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._json(405, {"message": "Pyramid only reads (GET)."})

    do_PUT = do_PATCH = do_DELETE = do_POST

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"message": "Unexpected Host header"})
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if "k" in q:  # first visit: trade the one-time key in the URL for a cookie
            if not self.server.take_url_key(q["k"][0]):
                return self._json(403, {"message": "This address has been used already: restart 'pyramid web' for a new one."})
            cookie = f"{self.server.cookie}={self.server.key}; HttpOnly; SameSite=Strict; Path=/"
            return self._send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})
        if u.path.startswith("/local/"):
            if not self._authed():
                return self._json(401, {"message": "Open the address printed by 'pyramid web' (it carries the session key)."})
            return self._local(u)
        body = _web_file(u.path)
        if body is None:
            return self._json(404, {"message": "Not found"})
        if u.path in ("", "/", "/index.html"):
            body = body.replace(b'<html lang="en">', b'<html lang="en" data-mode="local">', 1)
        ctype = mimetypes.guess_type(u.path if u.path not in ("", "/") else "index.html")[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype)

    def _local(self, u):
        if u.path == "/local/info":
            return self._json(200, {"mode": "local", "version": __version__, **self.server.info()})
        prefix = "/local/api/"
        if not u.path.startswith(prefix):
            return self._json(404, {"message": "Not found"})
        rest = u.path[len(prefix):]
        name, _, api_path = rest.partition("/")
        name = urllib.parse.unquote(name)
        api_path = "/" + api_path
        # plain characters only (no %-escapes), and no "." or ".." segment
        if not SAFE_API_PATH.match(api_path) or any(seg in (".", "..") for seg in api_path.split("/")):
            return self._json(400, {"message": "Only /api/v2/ paths are forwarded"})
        try:
            gc = self.server.client(name)
        except ValueError as e:  # e.g. a region this version does not know
            return self._json(400, {"message": str(e)})
        if gc is None:
            return self._json(404, {"message": f"No saved client named {name!r}"})
        url = api_path + (f"?{u.query}" if u.query else "")
        try:
            data = gc.get(url)
        except ApiError as e:
            return self._json(e.status or 502, {"message": e.message, "contextId": e.correlation_id})
        except Exception as e:  # network trouble etc.
            return self._json(502, {"message": str(e)})
        if isinstance(data, dict) and isinstance(data.get("nextUri"), str):
            # keep paging relative to this proxy
            nxt = data["nextUri"]
            if nxt.startswith("http"):
                nxt = urllib.parse.urlsplit(nxt)._replace(scheme="", netloc="").geturl()
            data["nextUri"] = nxt
        return self._json(200, data)


def make_server(port: int = 8710, store: Store | None = None) -> LocalServer:
    last: OSError | None = None
    for p in range(port, port + 20):
        try:
            return LocalServer(("127.0.0.1", p), store or Store())
        except OSError as e:  # port taken: try the next one
            last = e
    raise SystemExit(f"No free port from {port} to {port + 19}: {last}")


def _open_privately(url: str) -> None:
    """Open the browser on a private file that redirects to url, so the key in
    url never appears on a command line other users can list."""
    fd, path = tempfile.mkstemp(prefix="pyramid-web-", suffix=".html")  # 0600
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        target = html.escape(url, quote=True)
        f.write(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={target}">'
                f'<title>Pyramid</title><a href="{target}">Open Pyramid</a>')
    webbrowser.open(Path(path).as_uri())
    threading.Timer(60, lambda: os.path.exists(path) and os.unlink(path)).start()


def run(port: int = 8710, open_browser: bool = True) -> int:
    srv = make_server(port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/?k={srv.url_key}"
    if open_browser:
        print(f"Pyramid web on http://127.0.0.1:{srv.server_address[1]}/ (opening the browser)", flush=True)
        threading.Timer(0.3, _open_privately, args=(url,)).start()
    else:
        print(f"Pyramid web: open {url}\n(the address works once)", flush=True)
    print("Only this computer can reach it; Ctrl+C stops it.", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
