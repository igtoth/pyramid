# Changelog

## [2.1.2] - Current

### Changed
- Registry (`winreg`) replaced by `configparser` — credentials now stored in `%APPDATA%/Pyramid/pyramid.cfg`
- Fully portable: no longer Windows-only at the OS API level

### Added
- Light (Windows-native) theme as default
- Dark mode toggle in About tab
- Theme choice persisted in config file

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
