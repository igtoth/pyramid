@echo off
REM ─────────────────────────────────────────────────────────────────
REM  Pyramid API Management — Nuitka build script (Windows CMD)
REM  Usage: scripts\build.bat   (run from project root)
REM  Output: dist\pyramid.exe
REM
REM  Requirements:
REM    pip install "nuitka[onefile]"
REM    pip install -r requirements.txt
REM ─────────────────────────────────────────────────────────────────

cd /d "%~dp0.."

echo [*] Building Pyramid API Management with Nuitka...
echo.

python -m nuitka ^
    --mode=onefile ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=assets/pyramid.ico ^
    --enable-plugin=tk-inter ^
    --include-package=PureCloudPlatformClientV2 ^
    --include-package=PIL ^
    --include-distribution-metadata=PureCloudPlatformClientV2 ^
    --company-name="Pyramid" ^
    --product-name="Pyramid API Management" ^
    --file-version=2.1.2.0 ^
    --product-version=2.1.2.0 ^
    --copyright="MIT License - Use at your own risk" ^
    --output-filename=pyramid.exe ^
    --output-dir=dist ^
    --remove-output ^
    --assume-yes-for-downloads ^
    src/pyramid.py

echo.
if %ERRORLEVEL% == 0 (
    echo [OK] Build successful: dist\pyramid.exe
) else (
    echo [ERROR] Build failed with code %ERRORLEVEL%
)
