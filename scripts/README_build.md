# Build Instructions

## Requirements

```bash
pip install nuitka
pip install -r requirements.txt

# Windows: also needs a C compiler — easiest option:
# Download and install MinGW-w64 or Visual Studio Build Tools
# https://aka.ms/vs/17/release/vs_BuildTools.exe
```

## Build

```bat
scripts\build.bat
```

Output: `dist\pyramid.exe`

## What the flags do

| Flag | Purpose |
|---|---|
| `--onefile` | Single EXE, no folder |
| `--windows-disable-console` | No black terminal window |
| `--windows-icon-from-ico` | App icon |
| `--include-package=PureCloudPlatformClientV2` | Force-include SDK |
| `--include-package=PIL` | Force-include Pillow |
| `--enable-plugin=tk-inter` | Nuitka plugin for Tkinter support |
| `--assume-yes-for-downloads` | Auto-download MinGW if not found |

## Why Nuitka instead of PyInstaller?

Nuitka compiles Python to C and then to a native EXE.
It does **not** use a bootloader or extract files to `%TEMP%`.
This eliminates the false-positive antivirus detections that
PyInstaller executables commonly trigger.

## Antivirus note

If any AV still flags the EXE after building with Nuitka:

1. Scan on VirusTotal: https://www.virustotal.com
2. Submit false positive to Windows Defender:
   https://www.microsoft.com/en-us/wdsi/filesubmission
3. Reference the public source code in the report
