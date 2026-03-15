# /old — Project History

This directory preserves all previous versions of the Pyramid project, spanning 20 years of Genesys tooling.

## Timeline

```
2005  ──  legacy-2005-tserver/    Genesys T-Server auto-dialer & verifier (C / TLib)
2021  ──  v1-2021/                Pyramid v1.0 — simple PureCloud user/queue exporter
2025  ──  v2.1.1-pre-expansion/   Pyramid v2.1.1 — 21 API methods, winreg config
now   ──  ../src/pyramid.py       Pyramid v2.1.2 — 53 API methods, portable config
```

## Directories

### `legacy-2005-tserver/`
Two C source files (`dial.c`, `verify.c`) written against the Genesys TLib SDK. Auto-dialer with redial logic and a T-Server/PBX connectivity tester. Historical artifacts from early Genesys CTI work.

### `v1-2021/`
The first Pyramid release — distributed as a standalone `.exe` via Git LFS. Screenshot and LFS config preserved; binary not included.

### `v2.1.1-pre-expansion/`
The 21-method version before the v2.1.2 expansion to 53 methods. Includes the full Python source, tests (with `winreg` stubs), and documentation from that era.

| | v2.1.1 | v2.1.2 (current) |
|---|---|---|
| API methods | 21 | 53 |
| Sections | 6 | 12 |
| Lines of code | 3,366 | 4,038 |
| Config storage | `winreg` (Windows-only) | `configparser` (portable) |
| Build tool | PyInstaller | Nuitka |
| Terms of Use | — | First-run dialog |
