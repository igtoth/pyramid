"""pyramid web: the web page served on this computer, with the OAuth clients
saved in the desktop app.

The server listens on 127.0.0.1 only. The browser gets a random session key
once (in the URL it opens), kept in an HttpOnly, SameSite=Strict cookie;
every /local/ call needs it, and the Host header must be this server, so
other sites and DNS rebinding cannot reach the proxy. The proxy forwards
GETs to /api/v2/ only and adds the token itself: secrets never reach the page.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import secrets
import threading
import urllib.parse
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import __version__
from .client import ApiError, GenesysClient
from .config import Store

log = logging.getLogger(__name__)
COOKIE = "pyramid_session"


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, store: Store):
        super().__init__(addr, Handler)
        self.store = store
        self.key = secrets.token_urlsafe(32)
        self.clients: dict[str, GenesysClient] = {}
        self.lock = threading.Lock()

    def client(self, name: str) -> GenesysClient | None:
        with self.lock:
            self.store.reload()
            c = self.store.client(name)
            if not c:
                return None
            gc = self.clients.get(name)
            if gc is None or (gc.region, gc.client_id) != (c.region, c.client_id):
                gc = GenesysClient(c.region, c.client_id, c.client_secret, proxy=self.store.proxy())
                self.clients[name] = gc
            return gc


def _web_file(path: str) -> bytes | None:
    if path in ("", "/"):
        path = "index.html"
    path = path.lstrip("/")
    if path == "catalog.json":
        node = resources.files("pyramid").joinpath("catalog.json")
    else:
        if ".." in path or path.startswith("/") or "\\" in path:
            return None
        node = resources.files("pyramid").joinpath("web").joinpath(path)
    try:
        return node.read_bytes() if node.is_file() else None
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


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
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return COOKIE in c and secrets.compare_digest(c[COOKIE].value, self.server.key)

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
        if "k" in q:  # first visit: trade the key in the URL for a cookie
            if not secrets.compare_digest(q["k"][0], self.server.key):
                return self._json(403, {"message": "Wrong session key: open the address printed by 'pyramid web'."})
            cookie = f"{COOKIE}={self.server.key}; HttpOnly; SameSite=Strict; Path=/"
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
            store = self.server.store
            store.reload()
            clients = [{"name": c.name, "region": c.region} for c in store.clients()]
            return self._json(200, {"mode": "local", "version": __version__, "clients": clients,
                                    "last": store.get("last_client")})
        prefix = "/local/api/"
        if not u.path.startswith(prefix):
            return self._json(404, {"message": "Not found"})
        rest = u.path[len(prefix):]
        name, _, api_path = rest.partition("/")
        name = urllib.parse.unquote(name)
        api_path = "/" + api_path
        if not api_path.startswith("/api/v2/") or ".." in api_path:
            return self._json(400, {"message": "Only /api/v2/ paths are forwarded"})
        gc = self.server.client(name)
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


def run(port: int = 8710, open_browser: bool = True) -> int:
    srv = make_server(port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/?k={srv.key}"
    print(f"Pyramid web on {url}\n(only this computer can reach it; Ctrl+C stops it)", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
