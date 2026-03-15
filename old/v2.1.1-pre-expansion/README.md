# Pyramid API Management

A desktop GUI tool for querying and exporting data from **Genesys Cloud** via the PureCloudPlatformClientV2 SDK.

Built with Python + Tkinter. Runs on Windows and any OS with Python 3.9+.

---

## Features

- 🔐 **Credential manager** — stored in `%APPDATA%/Pyramid/pyramid.cfg` (no registry, portable)
- 📋 **21 API methods** across Users, Telephony, Routing, Security, Configuration and Integrations
- ⚡ **In-memory cache** — results reused across navigations; per-client keying
- 🔄 **Refresh on demand** — force new API call from any result page
- 🔍 **Search / filter** — live filter on all result tables
- ↕️ **Sortable columns** — click any column header
- 📤 **Export CSV / JSON**
- 🖱️ **Right-click → Copy cell value**
- ⌨️ **Keyboard shortcuts**: `[Esc]` back, `[Ctrl+S]` save CSV
- 📐 **Responsive card grid** — reflows 1→2→3 columns as window resizes
- 🌗 **Light / Dark theme toggle** — persisted in config
- 🌐 **Proxy support** — configurable proxy URL

---

## Requirements

| Dependency | Version |
|---|---|
| Python | ≥ 3.9 |
| PureCloudPlatformClientV2 | ≥ 197.0.0 |
| Pillow | ≥ 10.0.0 |

> No longer requires `winreg` — runs on Windows, Linux and macOS.

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/pyramid-api-manager.git
cd pyramid-api-manager

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
python src/gcmanager.py
```

---

## Build EXE (Windows)

```bash
pip install pyinstaller
pyinstaller scripts/build.spec
# Output: dist/gcmanager.exe
```

---

## Project Structure

```
pyramid-api-manager/
├── src/
│   └── gcmanager.py          # Main application
├── assets/
│   └── gcico.ico
├── docs/
│   ├── CHANGELOG.md
│   └── screenshots/
├── scripts/
│   ├── build.spec
│   └── version-file.txt
├── tests/
│   └── test_data_processing.py
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
├── .env.example
└── README.md
```

---

## Configuration File

Credentials are stored in:

```
%APPDATA%\Pyramid\pyramid.cfg        (Windows)
~/.config/Pyramid/pyramid.cfg        (Linux / macOS fallback)
```

Created automatically on first run. No registry keys used.

---

## API Methods

| Section | Method |
|---|---|
| Users | All Users, All Users + Queues, External Contacts, Groups, Teams |
| Telephony | Phone Numbers, Edge Devices, Sites, Trunks |
| Architect | All Flows, IVR Configurations, Schedules, Schedule Groups |
| Routing | All Queues, All Skills, Wrap-up Codes, Routing Languages |
| Security | OAuth Clients, Authorization Roles |
| Configuration | Organization Settings, License Users |
| Integrations | All Integrations |

---

## Changelog

See [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

---

## License

MIT

---

## Disclaimer

> **Use only with Genesys Cloud organizations where you hold valid administrative credentials and explicit permission.**
> Unauthorized access to third-party systems may violate applicable law (CFAA, Lei nº 12.737/2012, Computer Misuse Act, etc.).
>
> **This software is provided "as is", without warranty of any kind. USE AT YOUR OWN RISK.**
> The author accepts no liability for any direct, indirect, incidental or consequential damages arising from its use.
>
> Handling of personal data retrieved via this tool is the sole responsibility of the user,
> in compliance with applicable privacy law (LGPD, GDPR, etc.).

---

## What Pyramid does

### 📦 Full pagination — no record limits
Pyramid paginates the API automatically and fetches every record regardless of org size — users, queues, contacts, roles and more. Results are only limited by what the API returns.

### 💾 Saves directly to your filesystem
Exports are saved as CSV or JSON directly to any folder you choose. No size limits, no expiry, no inbox required. Files stay where you put them, named as you want.

### 🔗 Users + Queues in one export
Export a flat table of all users and all their queue memberships in a single CSV — one row per user, queues as a comma-separated column. Ready for Excel, Power BI or any reporting tool.

### ⚙ Config objects: IVRs, Flows, Schedules and more
Pyramid exports configuration objects that are not easily available through standard workflows:

| Object |
|---|
| IVR Configurations (DNIS → Flow mappings) |
| Architect Flows metadata |
| Schedules & Schedule Groups |
| OAuth Clients |
| Authorization Roles |
| Integrations |
| License Users |

### 🏢 Multiple orgs, one tool
Store credentials for as many orgs as you need and switch between them with a single click. Each org's data is cached independently in memory.

### ⚡ In-memory cache — instant re-open
Once a dataset is fetched, clicking the same button again opens it instantly from memory — no new API call. Use 🔄 Refresh only when you need fresh data.

### 📋 Raw JSON export
Every query can be exported as the raw API JSON response — useful for migration scripting, debugging, or feeding data into other tools.

### 🎯 Built for migrations & audits
Pyramid is purpose-built for getting a complete snapshot of an org's configuration at any point in time.

- Pre/post **migration comparison** between orgs
- **Security audit** (roles, OAuth clients, license usage)
- **Documentation** of a live org before making changes
- **Onboarding**: quickly understand an unknown org's setup

---

## Building the EXE (Windows)

### Requirements

```cmd
pip install "nuitka[onefile]"
pip install -r requirements.txt
```

### Quick build

```cmd
scripts\build.bat
```

Output: `dist\pyramid.exe`

### Manual command (CMD)

```cmd
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
    --output-filename=pyramid.exe ^
    --output-dir=dist ^
    --remove-output ^
    --assume-yes-for-downloads ^
    src/pyramid.py
```

### Notes

- First build takes **5–15 minutes** — Nuitka compiles Python to C then to native EXE
- Nuitka may download MinGW64 / ccache on first run (answer `yes`)
- `--enable-plugin=tk-inter` is required — without it the GUI will not render
- `zstandard` is required for onefile compression — installed via `nuitka[onefile]`
- The icon must exist at `assets/pyramid.ico` before building
- Subsequent builds are faster due to Nuitka's bytecode and C compilation cache

### PowerShell syntax

Replace `^` with a backtick `` ` `` for line continuation in PowerShell.

### Why Nuitka instead of PyInstaller?

Nuitka compiles Python to native C — no bootloader, no `%TEMP%` extraction.
This means **no false positives from antivirus** engines that flag PyInstaller's
packaging technique as suspicious.
