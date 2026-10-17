# Changelog

## [3.0.0] (2026-10-17)

A rewrite around one catalog of reports, shared by a new desktop app, a web
version and a command line.

### Added
- **Web version** at https://igtoth.github.io/pyramid/: saved orgs like the
  desktop OAuth tab (kept in the tab's session, or in the browser when
  remembered; nothing on any server), sign in with your Genesys Cloud
  account (OAuth PKCE, no secret), same reports, same exports.
- **`pyramid web`**: the web page on your computer with the clients saved in
  the desktop app; the secret stays in the Pyramid process.
- **Command line**: `pyramid export <reports...> | all`, CSV and/or JSON,
  with a saved client or `GC_*` environment variables; `pyramid list`,
  `pyramid clients`.
- **All Users + Roles**: every user with every role they hold, read per role.
- **Tabs in Main**: Reports is the first tab and each report opens in its
  own, closable (✕, middle-click, Ctrl+W); reopening a report switches to it.
- Every report: double-click a row for every field the API returned;
  right-click to copy a cell or the row; queue members from the queues report.
- Dark and light theme switch at once, no restart.
- Builds for Windows (installer and portable), macOS (Apple silicon and
  Intel) and Linux (AppImage and tar.gz) from GitHub Actions, with a nightly
  pre-release on every push to main.
- Regions: sa_east_1, mx_central_1, me_central_1, eu_central_2,
  eusc_de_east_1, ap_southeast_1 and ap_northeast_3 (18 in all).

### Changed
- Calls the Genesys Cloud REST API directly instead of the Python SDK, whose
  method renames had broken four buttons; the only runtime dependency is
  `certifi`. Raw JSON exports are now the API's own JSON (camelCase).
- All Users + Queues reads each queue's member list once instead of asking
  every user for their queues: far fewer calls, no rate-limit failures in
  large orgs. It now also lists inactive users and skills.
- Messaging Integrations, Gamification Metrics (now per performance profile)
  and Key Configurations (replaces Local Key Settings) use the current API;
  Report Exports replaces Reporting Schedules, which the API removed.
- Every listing pages to the end (email domains, web deployments and edges
  stopped at the first page before).
- The access token lives as long as Genesys says (`expires_in`) instead of a
  fixed 23 hours, and is renewed on a 401.
- CSV export: what you see (filter and order included), UTF-8 with BOM for
  Excel, cells that would run as formulas get a leading apostrophe; empty
  values are empty, not "N/A", and no columns appear that the API did not send.
- Settings file per platform (`%APPDATA%\Pyramid`, `~/Library/Application
  Support/Pyramid`, `~/.config/Pyramid`), private (0600) on macOS and Linux;
  v2 files are read and converted. Client names keep their case; `%` in a
  proxy URL or secret no longer breaks the start-up.
- A proxy set in Pyramid wins; otherwise the system proxy (`HTTPS_PROXY`,
  `NO_PROXY`) applies.

### Fixed
- Results of one org were shown, marked "cached", after switching to another.
- An error was cached as an empty result.
- The window was updated from worker threads; Cancel did not stop a request.
- Pressing Esc before choosing a client showed "Connected: PY_VAR0".
- The mouse wheel scrolled the wrong tab, and did nothing on Linux and macOS.
- Double-click on queues stopped working after an empty queue.
- Numbers sorted as text; the search lost the sort order.
- "Open config folder" only worked on Windows.
- The test suite did not run.

### Removed
- Calibrations: the API only lists calibrations of one calibrator.

## [2.1.2] (2025)

53 SDK methods in 12 sections, `configparser` instead of the registry, terms
of use dialog, Help tab, Nuitka build. Its source and full changelog are in
[`old/v2.1.2-sdk-tk/`](../old/v2.1.2-sdk-tk/).

## [2.1.1], [2.1.0], [2.0.0] (2024 and 2025)

Theme toggle, responsive card grid, in-memory cache, proxy setting, token
caching, retry on 429, search bar. See
[`old/v2.1.2-sdk-tk/CHANGELOG.md`](../old/v2.1.2-sdk-tk/CHANGELOG.md).

## [1.x] (2021 to 2024)

The first Pyramid: users and queues exporter. See [`old/`](../old/).
