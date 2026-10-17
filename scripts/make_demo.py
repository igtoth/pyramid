"""Write src/pyramid/web/demo.json, the made-up org the web page's demo mode
shows (the published site at igtoth.github.io/pyramid). Deterministic: run it
again after changing tests/fake_genesys.py or catalog.json.

    python scripts/make_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import fake_genesys  # noqa: E402

OUT = ROOT / "src/pyramid/web/demo.json"


def render() -> str:
    return json.dumps(fake_genesys.demo_data(), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} KB")
