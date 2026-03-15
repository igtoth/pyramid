# Pyramid API Management

A desktop GUI tool for querying and exporting data from **Genesys Cloud** via the PureCloudPlatformClientV2 SDK.

Built with Python + Tkinter. Runs on Windows and any OS with Python 3.9+.

> **This is NOT a Genesys product.** It is an independent, open-source utility.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

## Features

- 🔐 **Credential manager** — stored in `%APPDATA%/Pyramid/pyramid.cfg` (no registry, portable)
- 📋 **53 API methods** across 12 sections
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
- 📜 **Terms of Use dialog** — first-run legal agreement with MIT license, data privacy and authorized-use disclaimers
- 🧱 **Animated Sieve of Eratosthenes** pyramid logo in the About tab

---

## API Methods (53)

| Section | Methods |
|---------|---------|
| **Users, Teams & Directory** | All Users, All Users + Queues, External Contacts, Groups, Teams |
| **Telephony & Architect** | Phone Numbers (DIDs), Edge Devices, Sites, Trunks, All Flows, IVR Configurations, Schedules, Schedule Groups, Emergency Groups, User Prompts, Flow Milestones, Flow Outcomes, Data Tables |
| **Routing & Queues** | All Queues, All Skills, Wrap-up Codes, Routing Languages, Email Domains, SMS Addresses, Routing Utilization, Utilization Labels, Predictors |
| **Security** | OAuth Clients, Authorization Roles |
| **Configuration** | Organization Settings, License Users |
| **Integrations** | All Integrations, Messaging Integrations, Web Deployments, Web Deploy Configs |
| **Quality Management** | Evaluation Forms, Survey Forms, Calibrations |
| **Recording** | Recording Settings, Local Key Settings |
| **Outbound** | Campaigns, Contact Lists, DNC Lists, Call Analysis Response Sets, Sequences |
| **Workforce Management** | Business Units, Management Units |
| **Analytics & Stations** | Stations, Presence Definitions, Analytics Scheduled Reports |
| **Gamification** | Profiles, Metrics |

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
git clone https://github.com/igtoth/pyramid-api-management.git
cd pyramid-api-management

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
python src/pyramid.py
```

---

## Build EXE (Windows)

```bash
pip install "nuitka[onefile]"
pip install -r requirements.txt
scripts\build.bat
# Output: dist\pyramid.exe
```

See [`scripts/README_build.md`](scripts/README_build.md) for detailed build instructions.

### Why Nuitka instead of PyInstaller?

Nuitka compiles Python to native C — no bootloader, no `%TEMP%` extraction.
This means **no false positives from antivirus** engines that flag PyInstaller's
packaging technique as suspicious.

---

## Project Structure

```
pyramid-api-management/
├── src/
│   └── pyramid.py              # Main application (single-file)
├── assets/
│   └── pyramid.ico             # App icon (add before building)
├── docs/
│   └── CHANGELOG.md
├── scripts/
│   ├── build.bat               # Nuitka build script (Windows)
│   └── README_build.md         # Build documentation
├── tests/
│   └── test_data_processing.py # Unit tests for data processing
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
├── .env.example
├── LICENSE
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

The config file stores:

- OAuth client credentials (Client ID, Secret, Region)
- Proxy URL and enabled state
- Theme preference (dark/light)
- Terms acceptance flag

> **⚠ Security note:** Client secrets are stored in **plain text**. Protect the config file with OS-level permissions and avoid using this tool on shared machines.

---

## Usage

1. **First run** — accept the Terms of Use dialog.
2. **Add credentials** — go to the **OAuth** tab, fill in Name, Region, Client ID and Secret, click Save.
3. **Test connection** — click Test to verify the credentials work.
4. **Browse data** — switch to the **Main** tab, click any API method button.
5. **Export** — use the CSV or JSON export buttons, or press `Ctrl+S`.

### Genesys Cloud OAuth Setup

You need a **Client Credentials** grant type OAuth client in your Genesys Cloud org:

1. Go to **Admin → Integrations → OAuth**
2. Create a new OAuth client with grant type **Client Credentials**
3. Assign the required roles/permissions for the APIs you want to query
4. Copy the Client ID and Secret into Pyramid

---

## What Pyramid Does

### 📦 Full pagination — no record limits
Pyramid paginates the API automatically and fetches every record regardless of org size — users, queues, contacts, roles and more. Results are only limited by what the API returns.

### 💾 Saves directly to your filesystem
Exports are saved as CSV or JSON directly to any folder you choose. No size limits, no expiry, no inbox required.

### 🔗 Users + Queues in one export
Export a flat table of all users and all their queue memberships in a single CSV — one row per user, queues as a comma-separated column. Ready for Excel, Power BI or any reporting tool.

### ⚙ Config objects: IVRs, Flows, Schedules and more
Pyramid exports configuration objects not easily available through standard workflows:
IVR Configurations (DNIS → Flow mappings), Architect Flows metadata, Schedules & Schedule Groups, Emergency Groups, OAuth Clients, Authorization Roles, Integrations, License Users, Quality forms, Recording settings, Outbound campaigns, WFM units, Gamification profiles, and more.

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

## Changelog

See [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## License

[MIT](LICENSE)

---

## Author

**Ighor Toth**
- Email: [toth@ighor.com](mailto:toth@ighor.com)
- Website: [ighor.com](https://ighor.com)

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
