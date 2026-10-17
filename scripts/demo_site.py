"""Turn a copy of the web page into the demo the project publishes on GitHub
Pages: data-mode="demo" (made-up org from demo.json) and a Content Security
Policy that lets the page reach nothing but its own files.

    python scripts/demo_site.py site/index.html
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def make_demo(html: str) -> str:
    out = html.replace('<html lang="en">', '<html lang="en" data-mode="demo">', 1)
    out, n = re.subn(r"connect-src [^;]*;", "connect-src 'self';", out, count=1)
    if n != 1 or 'data-mode="demo"' not in out:
        raise SystemExit("index.html changed: update scripts/demo_site.py")
    return out


if __name__ == "__main__":
    path = Path(sys.argv[1])
    path.write_text(make_demo(path.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"{path}: demo mode, connect-src 'self'")
