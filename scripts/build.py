"""Build the desktop program with Nuitka and package it for this platform.

    pip install -r requirements-dev.txt
    python scripts/build.py [--version 3.0.0] [--skip-package]

Output in dist/:
  Windows  pyramid-<v>-windows-x86_64-setup.exe (Inno Setup, if ISCC is found)
           pyramid-<v>-windows-x86_64-portable.zip
  macOS    pyramid-<v>-macos-<arch>.dmg
  Linux    pyramid-<v>-linux-x86_64.AppImage, pyramid-<v>-linux-x86_64.tar.gz

Nuitka compiles Python to C: no bootloader unpacking into %TEMP%, which is
what makes antivirus engines flag many PyInstaller programs.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "nuitka"
DIST = ROOT / "dist"


def app_version() -> str:
    ns: dict = {}
    exec((ROOT / "src/pyramid/__init__.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def arch() -> str:
    m = platform.machine().lower()
    return {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(m, m)


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def nuitka(version: str) -> Path:
    numeric = ".".join((version.split("-")[0].split(".") + ["0", "0", "0"])[:4])
    cmd = [sys.executable, "-m", "nuitka",
           "--enable-plugin=tk-inter",
           "--include-package=pyramid",
           "--include-package-data=pyramid",
           "--nofollow-import-to=pytest,PIL,playwright,nuitka",
           f"--output-dir={BUILD}",
           "--assume-yes-for-downloads",
           "--remove-output",
           "--product-name=Pyramid", "--company-name=Ighor Toth",
           f"--file-version={numeric}", f"--product-version={numeric}",
           "--file-description=Pyramid: Genesys Cloud reports",
           "--copyright=MIT License, Ighor Toth"]
    if sys.platform == "win32":
        cmd += ["--mode=standalone", "--output-filename=pyramid.exe",
                "--windows-console-mode=attach",  # silent when double-clicked, prints when run from a terminal
                f"--windows-icon-from-ico={ROOT / 'assets/icon/pyramid.ico'}"]
    elif sys.platform == "darwin":
        # the package data folder "pyramid/" sits next to the program, and macOS file names ignore case
        cmd += ["--mode=app", "--output-filename=pyramid-app", "--macos-app-name=Pyramid",
                f"--macos-app-version={version}", f"--macos-app-icon={ROOT / 'assets/icon/pyramid.icns'}"]
    else:
        cmd += ["--mode=standalone", "--output-filename=Pyramid",  # "pyramid/" is the package data folder
                f"--linux-icon={ROOT / 'assets/icon/pyramid-256.png'}"]
    if BUILD.exists():
        shutil.rmtree(BUILD)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    run(cmd + [str(ROOT / "packaging/launcher.py")], env=env)
    if sys.platform == "darwin":
        apps = list(BUILD.glob("*.app"))
        assert apps, "no .app produced"
        return apps[0]
    dist = BUILD / "launcher.dist"
    assert dist.is_dir(), "no .dist folder produced"
    return dist


def package(out: Path, version: str) -> None:
    DIST.mkdir(exist_ok=True)
    if sys.platform == "win32":
        portable = DIST / f"pyramid-{version}-windows-x86_64-portable.zip"
        with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED) as z:
            for f in out.rglob("*"):
                z.write(f, Path("Pyramid") / f.relative_to(out))
            for extra in ("README.md", "LICENSE"):
                z.write(ROOT / extra, Path("Pyramid") / extra)
        iscc = shutil.which("ISCC") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        if Path(iscc).exists():
            run([iscc, f"/DVersion={version}", f"/DSrcDir={out}", str(ROOT / "packaging/windows/pyramid.iss")])
        else:
            print("Inno Setup not found: skipped the installer", flush=True)
    elif sys.platform == "darwin":
        run(["bash", str(ROOT / "packaging/macos/build-dmg.sh"), version, str(out), arch()])
    else:
        tgz = DIST / f"pyramid-{version}-linux-{arch()}.tar.gz"
        staged = BUILD / "pyramid"
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(out, staged)
        for extra in ("README.md", "LICENSE"):
            shutil.copy(ROOT / extra, staged / extra)
        run(["tar", "-C", str(BUILD), "-czf", str(tgz), "pyramid"])
        run(["bash", str(ROOT / "packaging/linux/build-appimage.sh"), version, str(out)])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=app_version())
    ap.add_argument("--skip-package", action="store_true")
    a = ap.parse_args()
    out = nuitka(a.version)
    print("built", out, flush=True)
    if not a.skip_package:
        package(out, a.version)
        for f in sorted(DIST.iterdir()):
            print(f"  {f.name}  {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
