"""Drive the real desktop app against the fake Genesys Cloud and capture
the README screenshots (and fail loudly if a screen does not come up).

Linux, under Xvfb:
    xvfb-run -s "-screen 0 1440x900x24" python scripts/screenshots.py docs/images

Every org, person and number in the pictures is made up (tests/fake_genesys.py).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import fake_genesys as fg  # noqa: E402

srv, url = fg.serve()
os.environ.update(PYRAMID_API_BASE=url, PYRAMID_LOGIN_BASE=url,
                  PYRAMID_CONFIG_DIR=tempfile.mkdtemp(prefix="pyramid-shots-"))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from pyramid import gui  # noqa: E402
from pyramid.config import OAuthClient, Store  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")
OUT.mkdir(parents=True, exist_ok=True)

store = Store()
store.put_client(OAuthClient("Lumen Harbor (prod)", "eu_central_1", fg.CLIENT_ID, fg.CLIENT_SECRET))
store.put_client(OAuthClient("Lumen Harbor (test)", "eu_central_1", fg.CLIENT_ID, fg.CLIENT_SECRET))
store.set("terms_accepted", True)
store.set("last_client", "Lumen Harbor (prod)")

root = tk.Tk()
root.geometry("1360x820+0+0")
app = gui.App(root, store)
root.geometry("1360x820+0+0")


def shot(name: str) -> None:
    root.update()
    time.sleep(0.4)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY")).save(OUT / name, quality=88)
    print("saved", OUT / name, flush=True)


def wait_idle(timeout=30):
    end = time.time() + timeout
    while app.busy and time.time() < end:
        root.update()
        time.sleep(0.05)
    if app.busy:
        raise SystemExit("task did not finish")
    root.update()


def open_report(key, force=False):
    ep = app.cat[key]
    app.open_report(ep, force=force) if not ep.slow else _open_slow(ep)
    wait_idle()
    assert app.current is not None and app.current.res.endpoint.key == key, f"{key} did not open"


def _open_slow(ep):
    gui.messagebox.askyesno = lambda *a, **k: True
    app.open_report(ep)


steps = []
try:
    # 1. the reports, light theme
    root.update()
    app.show_home()
    shot("pyramid-home.jpg")
    # 2. users + queues, searched and sorted
    open_report("usersqueues")
    app.current.table.sort(0)
    shot("pyramid-users-queues.jpg")
    # 3. several reports in their own tabs, dark theme
    app.set_theme("dark")
    open_report("trunks")
    open_report("queues")
    open_report("ivrs")
    shot("pyramid-tabs-dark.jpg")
    # 4. users + roles, filtered, dark
    open_report("usersroles")
    app.current.table.query.set("supervisor")
    shot("pyramid-users-roles-dark.jpg")
    # 5. org settings as key/value
    app.set_theme("light")
    open_report("settings")
    shot("pyramid-settings.jpg")
    # 6. OAuth tab
    app.nb.select(app.tab_oauth)
    shot("pyramid-oauth.jpg")
    # 7. About, dark
    app.set_theme("dark")
    app.nb.select(app.tab_about)
    for _ in range(40):
        root.update()
        time.sleep(0.05)
    shot("pyramid-about-dark.jpg")
    # tabs: reopening selects, closing falls back, close all goes home
    n = len(app.tabs)
    open_report("trunks")
    assert len(app.tabs) == n and app.current.res.endpoint.key == "trunks"
    app.close_current()
    assert app.current is not None and len(app.tabs) == n - 1
    app.close_all_tabs()
    assert app.current is None and not app.tabs
    # a failing event does not stop the window from processing the next ones
    seen = []
    app.events.put(("call", lambda: 1 / 0))
    app.events.put(("call", lambda: seen.append("after")))
    for _ in range(20):
        root.update()
        time.sleep(0.05)
    assert seen == ["after"] and not app.busy, "event loop stopped after an error"
    # every report opens without error
    app.set_theme("light")
    gui.messagebox.askyesno = lambda *a, **k: True
    for ep in app.cat.endpoints:
        app.open_report(ep, force=True)
        wait_idle()
        assert app.current.res.endpoint.key == ep.key, ep.key
        assert app.current.table is not None, ep.key
    assert len(app.tabs) == app.MAX_TABS, len(app.tabs)
    print(f"all {len(app.cat)} reports opened in the window; {len(app.tabs)} tabs kept", flush=True)
finally:
    root.destroy()
    srv.shutdown()
