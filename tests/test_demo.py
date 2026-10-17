import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_site  # noqa: E402
import make_demo  # noqa: E402

from pyramid.catalog import load  # noqa: E402


def test_demo_json_is_up_to_date():
    assert make_demo.OUT.read_text(encoding="utf-8") == make_demo.render(), "run: python scripts/make_demo.py"


def test_demo_has_every_report():
    data = json.loads(make_demo.OUT.read_text(encoding="utf-8"))
    for ep in load().endpoints:
        if ep.path:
            assert ep.path in data["listings"] or ep.path in data["objects"], ep.path
    assert "SHOULD-NEVER-APPEAR" in json.dumps(data)  # the page must strip it, as with a real org


def test_demo_site_reaches_nothing():
    html = (ROOT / "src/pyramid/web/index.html").read_text(encoding="utf-8")
    out = demo_site.make_demo(html)
    assert 'data-mode="demo"' in out and "connect-src 'self';" in out and "pure.cloud" not in out
