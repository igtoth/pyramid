"""End-to-end check of the web page in a real Chromium, against the fake
Genesys Cloud, in both modes; also captures the README pictures.

    pip install playwright && playwright install chromium
    python scripts/web_check.py docs/images

1. local: 'pyramid web' with a saved client (the proxy adds the token)
2. hosted: the static site (as GitHub Pages serves it) with PKCE sign-in
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import fake_genesys as fg  # noqa: E402

srv, fake_url = fg.serve()
os.environ.update(PYRAMID_API_BASE=fake_url, PYRAMID_LOGIN_BASE=fake_url,
                  PYRAMID_CONFIG_DIR=tempfile.mkdtemp(prefix="pyramid-web-"))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from pyramid.config import OAuthClient, Store  # noqa: E402
from pyramid.webserver import make_server  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")
OUT.mkdir(parents=True, exist_ok=True)
errors: list[str] = []


def build_site() -> Path:
    """The folder the Pages job publishes (see .github/workflows/build.yml)."""
    site = Path(tempfile.mkdtemp(prefix="pyramid-site-")) / "pyramid"   # served under /pyramid/ like Pages
    shutil.copytree(ROOT / "src/pyramid/web", site, dirs_exist_ok=True)
    shutil.copy(ROOT / "src/pyramid/catalog.json", site / "catalog.json")
    # the published page only talks to Genesys Cloud; let this test copy reach the fake on 127.0.0.1
    index = site / "index.html"
    text = index.read_text(encoding="utf-8")
    assert "https://*.eusc-pure.cloud;" in text
    index.write_text(text.replace("https://*.eusc-pure.cloud;", "https://*.eusc-pure.cloud http://127.0.0.1:*;"), encoding="utf-8")
    return site


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def static_server(folder: Path):
    handler = functools.partial(Quiet, directory=str(folder))
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}/pyramid/"


def watch(page):
    page.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)


def open_report(page, label):
    page.locator(".home .section button", has_text=label).first.click()
    expect(page.locator(".report:not([hidden]) h2")).to_have_text(label, timeout=20000)


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ── 1. local mode ──────────────────────────────────────────────────────
    store = Store()
    store.put_client(OAuthClient("Lumen Harbor (prod)", "eu_central_1", fg.CLIENT_ID, fg.CLIENT_SECRET))
    local = make_server(8790, store)
    threading.Thread(target=local.serve_forever, daemon=True).start()
    port = local.server_address[1]
    page = browser.new_page(viewport={"width": 1360, "height": 820}, accept_downloads=True)
    watch(page)
    # without the session key, the proxy refuses
    r = page.request.get(f"http://127.0.0.1:{port}/local/info")
    assert r.status == 401, r.status
    page.goto(f"http://127.0.0.1:{port}/?k={local.url_key}")
    page.get_by_role("button", name="Connect").click()
    expect(page.locator("#org")).to_contain_text("Lumen Harbor Telecom")
    page.screenshot(path=str(OUT / "pyramid-web-home.jpg"), quality=88)
    page.on("dialog", lambda d: d.accept())  # the "can take minutes" confirm
    open_report(page, "All Users + Queues")
    expect(page.locator(".report:not([hidden]) .count")).to_have_text("64 records")
    page.locator(".report:not([hidden])").get_by_role("columnheader", name="Name", exact=True).click()
    open_report_tab = page.locator(".subtabs .tab", has_text="Reports")
    open_report_tab.click()
    open_report(page, "Trunks")
    open_report_tab.click()
    open_report(page, "All Queues")
    expect(page.locator(".subtabs .tab")).to_have_count(4)
    page.locator(".report:not([hidden]) tbody tr").first.click()
    page.get_by_role("button", name="Show queue members").click()
    expect(page.locator("#dialog-title")).to_contain_text("Members of")
    page.keyboard.press("Escape")
    with page.expect_download() as dl:
        page.locator(".report:not([hidden]) button", has_text="Export CSV").click()
    csv_text = Path(dl.value.path()).read_text(encoding="utf-8-sig")
    assert csv_text.splitlines()[0].startswith("Name,Division,Member Count"), csv_text.splitlines()[0]
    page.locator(".subtabs .tab", has_text="All Users + Queues").click()
    page.locator(".report:not([hidden]) input[type=search]").fill("billing")
    page.screenshot(path=str(OUT / "pyramid-web-users-queues.jpg"), quality=88)
    page.locator(".subtabs .tab", has_text="Trunks").locator(".close").click()
    expect(page.locator(".subtabs .tab")).to_have_count(3)
    # OAuth client secrets never reach the page
    open_report_tab.click()
    open_report(page, "OAuth Clients")
    assert "SHOULD-NEVER-APPEAR" not in page.content()
    # every report opens
    for ep in [e for e in __import__("pyramid.catalog", fromlist=["load"]).load().endpoints]:
        open_report_tab.click()
        open_report(page, ep.label)
    print("local mode: every report opened; tabs kept:", page.locator(".subtabs .tab").count() - 1, flush=True)
    local.shutdown()

    # ── 2. hosted mode (GitHub Pages) with PKCE ──────────────────────────
    site = build_site()
    ss, site_url = static_server(site.parent)
    page = browser.new_page(viewport={"width": 1360, "height": 820}, color_scheme="dark")
    watch(page)
    page.goto(site_url + f"?api={fake_url}")
    expect(page.locator("#connect h1")).to_be_visible()
    page.screenshot(path=str(OUT / "pyramid-web-signin-dark.jpg"), quality=88)
    page.fill("#f-client", fg.CLIENT_ID)
    page.get_by_role("button", name="Sign in with Genesys Cloud").click()
    expect(page.locator("#org")).to_contain_text("Lumen Harbor Telecom", timeout=15000)
    open_report(page, "IVR Configurations")
    open_report_tab = page.locator(".subtabs .tab", has_text="Reports")
    open_report_tab.click()
    open_report(page, "Organization Settings")
    expect(page.locator(".report:not([hidden]) .count")).to_have_text("14 fields")
    page.locator(".subtabs .tab", has_text="IVR Configurations").click()
    page.screenshot(path=str(OUT / "pyramid-web-ivrs-dark.jpg"), quality=88)
    # phone width: no horizontal page scroll
    page.set_viewport_size({"width": 390, "height": 800})
    wide = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    assert not wide, "page scrolls sideways at phone width"
    print("hosted mode: PKCE sign-in and reports OK", flush=True)
    ss.shutdown()
    browser.close()

srv.shutdown()
if errors:
    print("\n".join(errors))
    raise SystemExit("browser errors")
print("web check passed")
