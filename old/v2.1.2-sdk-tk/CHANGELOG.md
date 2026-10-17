# Changelog

## [2.1.2] - Current

### Changed
- Registry (`winreg`) replaced by `configparser` — credentials now stored in `%APPDATA%/Pyramid/pyramid.cfg`
- Fully portable: no longer Windows-only at the OS API level
- Light (Windows-native) theme as default

### Added
- **32 new API methods** (total now 53 across 12 sections):
  - Emergency Groups, User Prompts, Flow Milestones, Flow Outcomes, Data Tables
  - Email Domains, SMS Addresses, Routing Utilization, Utilization Labels, Predictors
  - Messaging Integrations, Web Deployments, Web Deploy Configs
  - Evaluation Forms, Survey Forms, Calibrations
  - Recording Settings, Local Key Settings
  - Outbound Campaigns, Contact Lists, DNC Lists, Call Analysis Response Sets, Sequences
  - WFM Business Units, WFM Management Units
  - Stations, Presence Definitions, Analytics Scheduled Reports
  - Gamification Profiles, Gamification Metrics
- **Terms of Use dialog** on first run — covers authorized use, data privacy, no warranty, credential storage, and MIT license
- Terms acceptance persisted in `pyramid.cfg`
- Dark mode toggle in About tab; theme persisted in config
- Animated Sieve of Eratosthenes pyramid logo in About tab
- Built-in **Help tab** with full reference documentation for all 53 methods

---

## [2.1.1]

### Added
- Back button returns to **Main tab** regardless of active tab
- Section cards responsive: reflow 1→2→3 columns on window resize
- In-memory result cache keyed by `(client_id, method)`
- 🔄 Refresh button on every result page
- Cache badge (`⚡ cached` / `🌐 live`) in result header

---

## [2.1.0]

### Added
- Removed company-specific branding; proxy URL user-configurable
- Full visual overhaul: custom `ttk.Style`, hover/press animations, colour-coded section cards, alternating table rows

---

## [2.0.0]

### Added
- Token caching (23h TTL)
- Generic `_paginate()` with 429 exponential back-off
- 13 new SDK methods: Groups, Teams, Sites, Trunks, DIDs, IVRs, Schedules, Schedule Groups, Wrap-up Codes, Languages, OAuth Clients, Authorization Roles, Integrations
- Search/filter bar on all result tables
- Right-click → Copy cell value
- Keyboard shortcuts: `[Esc]` back, `[Ctrl+S]` save CSV

---

## [1.x.x] - 2024

- Initial releases
