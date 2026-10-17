"""A small Genesys Cloud REST client: client-credentials auth, retries,
rate-limit handling and pagination. Standard library only (plus certifi
for CA certificates when it is installed)."""

from __future__ import annotations

import base64
import email.utils
import json
import logging
import random
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from . import __version__, regions

log = logging.getLogger(__name__)

USER_AGENT = f"Pyramid/{__version__} (+https://github.com/igtoth/pyramid)"
MAX_PAGES = 10_000


class Cancelled(Exception):
    """The user cancelled the running request."""


class ApiError(Exception):
    """A request the API answered with an error, or that never got an answer."""

    def __init__(self, status: int | None, message: str, correlation_id: str | None = None):
        self.status = status
        self.message = message
        self.correlation_id = correlation_id
        text = f"HTTP {status}: {message}" if status else message
        if correlation_id:
            text += f" (correlation id {correlation_id})"
        super().__init__(text)


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover - certifi is a declared dependency
        return ssl.create_default_context()


class CancelToken:
    """A threading.Event with a sleep that wakes up when cancelled."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()

    def sleep(self, seconds: float) -> None:
        if self._event.wait(seconds):
            raise Cancelled()


ProgressFn = Callable[[str], None]


class GenesysClient:
    """GET-only client for one org (one region + one OAuth client)."""

    def __init__(
        self,
        region: str,
        client_id: str,
        client_secret: str,
        proxy: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 6,
        backoff_cap: float = 60.0,
    ):
        self.region = region
        self.client_id = client_id
        self._secret = client_secret
        self.api_base = regions.api_base(region)
        self.login_base = regions.login_base(region)
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_cap = backoff_cap
        handlers: list[Any] = [urllib.request.HTTPSHandler(context=_ssl_context())]
        # A proxy set in Pyramid wins; otherwise the system's (HTTPS_PROXY / NO_PROXY) applies.
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else None))
        self._opener = urllib.request.build_opener(*handlers)
        self._token: str | None = None
        self._token_expires = 0.0
        self._lock = threading.Lock()
        self.calls = 0

    def __repr__(self) -> str:  # never show the secret
        return f"GenesysClient(region={self.region!r}, client_id={self.client_id[:8]!r}...)"

    # ── auth ──────────────────────────────────────────────────────────────

    def token(self, force: bool = False) -> str:
        with self._lock:
            if not force and self._token and time.time() < self._token_expires:
                return self._token
            basic = base64.b64encode(f"{self.client_id}:{self._secret}".encode()).decode()
            body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
            req = urllib.request.Request(
                f"{self.login_base}/oauth/token", data=body, method="POST",
                headers={"Authorization": f"Basic {basic}",
                         "Content-Type": "application/x-www-form-urlencoded",
                         "User-Agent": USER_AGENT})
            for attempt in range(self.max_retries + 1):
                try:
                    data = self._send(req, what="authentication")
                    break
                except ApiError as e:
                    if e.status in (429, 502, 503, 504) and attempt < self.max_retries:
                        time.sleep(min(self.backoff_cap, 2 ** attempt + random.random()))
                        continue
                    raise
            self._token = data["access_token"]
            # Keep a minute of margin; the lifetime is set per OAuth client.
            self._token_expires = time.time() + max(60, int(data.get("expires_in", 3600)) - 60)
            log.info("Token acquired, valid for %ss", data.get("expires_in"))
            return self._token

    def token_expires_in(self) -> int:
        return max(0, int(self._token_expires - time.time())) if self._token else 0

    # ── transport ─────────────────────────────────────────────────────────

    def _send(self, req: urllib.request.Request, what: str = "request") -> Any:
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise _api_error(e) from None
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            raise ApiError(None, f"Cannot reach Genesys Cloud for {what}: {reason}") from None
        except (TimeoutError, OSError) as e:
            raise ApiError(None, f"Network error during {what}: {e}") from None

    def url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if path.startswith("http"):
            url = path
        else:
            url = self.api_base + path
        if params:
            qs = urllib.parse.urlencode(_query_pairs(params))
            url += ("&" if "?" in url else "?") + qs
        return url

    def get(self, path: str, params: dict[str, Any] | None = None,
            cancel: CancelToken | None = None, progress: ProgressFn | None = None) -> Any:
        """GET a path or absolute URL; retries 429, 5xx and network errors, refreshes an expired token once."""
        url = self.url(path, params)
        refreshed = False
        attempt = 0
        while True:
            if cancel:
                cancel.check()
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self.token()}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT})
            self.calls += 1
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if e.code == 401 and not refreshed:
                    refreshed = True
                    self.token(force=True)
                    continue
                if e.code in (429, 502, 503, 504) and attempt < self.max_retries:
                    wait = _retry_after(e) or min(self.backoff_cap, 2 ** attempt + random.random())
                    attempt += 1
                    msg = f"HTTP {e.code}, retrying in {wait:.0f}s ({attempt}/{self.max_retries})"
                    log.warning(msg)
                    if progress:
                        progress(msg)
                    (cancel.sleep if cancel else time.sleep)(wait)
                    continue
                raise _api_error(e) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < self.max_retries:
                    wait = min(self.backoff_cap, 2 ** attempt + random.random())
                    attempt += 1
                    log.warning("Network error (%s), retrying in %.0fs", e, wait)
                    if progress:
                        progress(f"Network error, retrying in {wait:.0f}s")
                    (cancel.sleep if cancel else time.sleep)(wait)
                    continue
                raise ApiError(None, f"Network error: {getattr(e, 'reason', e)}") from None

    # ── pagination ────────────────────────────────────────────────────────

    def pages(self, path: str, params: dict[str, Any] | None = None, page_size: int | None = 100,
              size_param: str = "pageSize", cursor: bool = False, cancel: CancelToken | None = None,
              progress: ProgressFn | None = None, label: str = "") -> Iterator[dict[str, Any]]:
        """Yield every page of a listing.

        Page-number listings (with pageCount) are walked by pageNumber;
        cursor listings (cursor=True, or no pageCount) are walked by
        nextUri; anything else is one page.
        """
        params = dict(params or {})
        if page_size:
            params[size_param] = page_size
        number_paging = not cursor
        page = 1
        next_url: str | None = None
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            if next_url:
                data = self.get(next_url, None, cancel, progress)
            else:
                p = dict(params)
                if number_paging and page_size:
                    p["pageNumber"] = page
                data = self.get(path, p, cancel, progress)
            yield data
            if not isinstance(data, dict):
                return
            count = data.get("pageCount")
            if progress:
                done = f"{page}/{count}" if count else f"{page}"
                progress(f"{label} page {done}".strip())
            # walk by pageNumber only when we sent one; otherwise the same URL would come back
            if isinstance(count, int) and next_url is None and number_paging and page_size:
                if page >= count or not data.get("entities"):
                    return
                page += 1
                continue
            nxt = data.get("nextUri")
            if not nxt or nxt in seen or not data.get("entities"):
                return
            seen.add(nxt)
            number_paging = False
            next_url = nxt if nxt.startswith("http") else self.api_base + nxt
            page += 1
        raise ApiError(None, f"Stopped after {MAX_PAGES} pages of {path}")

    def entities(self, path: str, **kw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """All entities of a listing, and the raw pages they came from."""
        raw, out = [], []
        for page in self.pages(path, **kw):
            raw.append(page)
            out.extend(page.get("entities") or [])
        return out, raw


def _query_pairs(params: dict[str, Any]) -> list[tuple[str, str]]:
    pairs = []
    for k, v in params.items():
        if v is None:
            continue
        for item in (v if isinstance(v, (list, tuple)) else [v]):
            pairs.append((k, "true" if item is True else "false" if item is False else str(item)))
    return pairs


RETRY_AFTER_CAP = 120.0


def _retry_after(e: urllib.error.HTTPError) -> float | None:
    """Seconds to wait from Retry-After (seconds or an HTTP date), between 1 s and 2 min."""
    value = e.headers.get("Retry-After") if e.headers else None
    if not value:
        return None
    try:
        secs = float(value)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value)
            secs = when.timestamp() - time.time()
        except (TypeError, ValueError):
            return None
    return min(RETRY_AFTER_CAP, max(1.0, secs))


def _api_error(e: urllib.error.HTTPError) -> ApiError:
    corr = e.headers.get("inin-correlation-id") if e.headers else None
    message = e.reason or "error"
    try:
        body = json.loads(e.read() or b"{}")
        message = body.get("message") or body.get("error_description") or body.get("error") or message
        corr = corr or body.get("contextId")
    except Exception:
        pass
    return ApiError(e.code, str(message), corr)
