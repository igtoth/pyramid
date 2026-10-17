"""Draw the Pyramid icon (a pyramid of bricks, prime-numbered bricks in gold)
and write every size the packages need. Needs Pillow (a dev dependency).

    python scripts/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ROWS = 8


def primes(n: int) -> set[int]:
    s = [True] * (n + 1)
    s[0] = s[1] = False
    for i in range(2, int(n ** 0.5) + 1):
        if s[i]:
            for j in range(i * i, n + 1, i):
                s[j] = False
    return {i for i, p in enumerate(s) if p}


def draw(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.06
    # rounded tile behind the pyramid
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=size * 0.2, fill=(22, 24, 31, 255))
    inner = size - 2 * pad
    bw = inner * 0.82 / ROWS
    bh = bw * 0.62
    gap = max(1, size * 0.006)
    base_y = pad + inner * 0.76
    left = (size - bw * ROWS) / 2
    prime = primes(ROWS * (ROWS + 1) // 2)
    n = 0
    for r in range(ROWS):
        for c in range(ROWS - r):
            n += 1
            x0 = left + c * bw + r * bw / 2
            y0 = base_y - (r + 1) * bh
            fill = (255, 205, 60, 255) if n in prime else (205, 133, 63, 255)
            d.rounded_rectangle([x0 + gap, y0 + gap, x0 + bw - gap, y0 + bh - gap],
                                radius=max(1, bh * 0.18), fill=fill)
    return img


def main() -> None:
    big = draw(1024)
    icon_dir = ROOT / "assets" / "icon"
    icon_dir.mkdir(parents=True, exist_ok=True)
    pkg = ROOT / "src" / "pyramid" / "assets"
    pkg.mkdir(parents=True, exist_ok=True)
    web = ROOT / "src" / "pyramid" / "web"
    for s in (16, 32, 48, 64, 128, 256, 512, 1024):
        im = big.resize((s, s), Image.LANCZOS)
        im.save(icon_dir / f"pyramid-{s}.png")
        if s in (16, 32, 64, 256):
            im.save(pkg / f"pyramid-{s}.png")
    big.resize((256, 256), Image.LANCZOS).save(icon_dir / "pyramid.ico",
                                               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(icon_dir / "pyramid.icns")
    big.resize((192, 192), Image.LANCZOS).save(web / "icon-192.png")
    big.resize((32, 32), Image.LANCZOS).save(web / "favicon.png")
    print("icons written to", icon_dir)


if __name__ == "__main__":
    main()
