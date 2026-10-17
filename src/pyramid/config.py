"""Saved OAuth clients and settings in pyramid.cfg.

Locations:
  Windows  %APPDATA%\\Pyramid\\pyramid.cfg
  macOS    ~/Library/Application Support/Pyramid/pyramid.cfg
  Linux    $XDG_CONFIG_HOME/Pyramid/pyramid.cfg (default ~/.config)
PYRAMID_CONFIG_DIR overrides the folder.

Secrets are stored in plain text, as before; on macOS and Linux the file is
readable by its owner only (0600). Files written by v2 ([clients] with
"name = region,id,secret" and [Settings] terms_accepted) are read and
converted on the next save.
"""

from __future__ import annotations

import configparser
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CLIENT_PREFIX = "client:"
log = logging.getLogger("pyramid.config")


@dataclass
class OAuthClient:
    name: str
    region: str
    client_id: str
    client_secret: str


def config_dir() -> Path:
    override = os.environ.get("PYRAMID_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Pyramid"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Pyramid"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Pyramid"


def _legacy_file() -> Path | None:
    """v2 used ~/Pyramid when APPDATA was not set (macOS and Linux)."""
    if sys.platform == "win32" or os.environ.get("PYRAMID_CONFIG_DIR"):
        return None
    p = Path.home() / "Pyramid" / "pyramid.cfg"
    return p if p.is_file() else None


def _set_client(cp: configparser.RawConfigParser, c: OAuthClient) -> None:
    s = CLIENT_PREFIX + c.name
    if not cp.has_section(s):
        cp.add_section(s)
    cp.set(s, "region", c.region)
    cp.set(s, "client_id", c.client_id)
    cp.set(s, "client_secret", c.client_secret)


def _parser() -> configparser.RawConfigParser:
    cp = configparser.RawConfigParser(interpolation=None)  # '%' in URLs and secrets is fine
    cp.optionxform = str  # keep the case of names
    return cp


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config_dir() / "pyramid.cfg"
        self._cp = _parser()
        self._stamp: tuple | None = None
        self.reload()

    # ── file ──────────────────────────────────────────────────────────────

    def _file_stamp(self) -> tuple | None:
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def reload(self) -> None:
        """Read the file into a new parser, then swap it in at once (readers never see it half-filled)."""
        cp = _parser()
        source = self.path if self.path.is_file() else _legacy_file()
        if source:
            cp.read(source, encoding="utf-8")
        self._migrate(cp)
        self._stamp = self._file_stamp()
        self._cp = cp

    def reload_if_changed(self) -> None:
        if self._file_stamp() != self._stamp:
            self.reload()

    def _migrate(self, cp: configparser.RawConfigParser) -> None:
        if cp.has_section("clients"):  # v2: name = region,id,secret
            for name, value in cp.items("clients"):
                parts = value.split(",", 2)
                if len(parts) == 3 and not cp.has_section(CLIENT_PREFIX + name):
                    _set_client(cp, OAuthClient(name, *[p.strip() for p in parts]))
            cp.remove_section("clients")
        if cp.has_section("Settings"):  # v2 terms flag lived in [Settings]
            for k, v in cp.items("Settings"):
                if not cp.has_section("settings"):
                    cp.add_section("settings")
                cp.set("settings", k, v)
            cp.remove_section("Settings")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".pyramid-", suffix=".cfg", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                self._cp.write(f)
            if os.name == "posix":
                os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self._stamp = self._file_stamp()
        self._protect_legacy()

    def _protect_legacy(self) -> None:
        """v2 left ~/Pyramid/pyramid.cfg readable by everyone, secrets included.
        Its content now lives in the new file: make the old one private."""
        old = _legacy_file()
        if old and old.resolve() != self.path.resolve() and os.name == "posix":
            try:
                if os.stat(old).st_mode & 0o077:
                    os.chmod(old, 0o600)
                    log.warning("Made the v2 settings file %s private (0600); it can be deleted", old)
            except OSError:
                pass

    def _ensure(self, section: str) -> None:
        if not self._cp.has_section(section):
            self._cp.add_section(section)

    # ── clients ───────────────────────────────────────────────────────────

    def clients(self) -> list[OAuthClient]:
        out = []
        for s in self._cp.sections():
            if s.startswith(CLIENT_PREFIX):
                g = self._cp[s]
                out.append(OAuthClient(s[len(CLIENT_PREFIX):], g.get("region", ""),
                                       g.get("client_id", ""), g.get("client_secret", "")))
        return sorted(out, key=lambda c: c.name.lower())

    def client(self, name: str) -> OAuthClient | None:
        for c in self.clients():
            if c.name == name:
                return c
        for c in self.clients():  # names typed on the command line
            if c.name.lower() == name.lower():
                return c
        return None

    def _set_client_section(self, c: OAuthClient) -> None:
        _set_client(self._cp, c)

    def put_client(self, c: OAuthClient, old_name: str | None = None) -> None:
        name = c.name.strip()
        if not name or any(ch in name for ch in "[]\n\r"):
            raise ValueError("Client name cannot be empty or contain [, ] or line breaks")
        c.name = name
        if old_name and old_name != name:
            self._cp.remove_section(CLIENT_PREFIX + old_name)
        self._set_client_section(c)
        self.save()

    def delete_client(self, name: str) -> None:
        if self._cp.remove_section(CLIENT_PREFIX + name):
            self.save()

    # ── settings ──────────────────────────────────────────────────────────

    def get(self, key: str, default: str = "") -> str:
        return self._cp.get("settings", key, fallback=default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key, "")
        return default if v == "" else v.strip().lower() in ("1", "true", "yes", "on")

    def set(self, key: str, value: str | bool, save: bool = True) -> None:
        self._ensure("settings")
        self._cp.set("settings", key, ("1" if value else "0") if isinstance(value, bool) else str(value))
        if save:
            self.save()

    def proxy(self) -> str | None:
        url = self.get("proxy_url").strip()
        return url if url and self.get_bool("proxy_enabled") else None


def valid_proxy(url: str) -> bool:
    return url == "" or url.startswith(("http://", "https://"))


def redact_url(url: str) -> str:
    """http://user:pass@proxy:8080 -> http://***@proxy:8080, for logs and screens."""
    if not url or "@" not in url:
        return url or ""
    scheme, sep, rest = url.partition("://")
    if not sep:
        return "***@" + url.rsplit("@", 1)[1]
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"
