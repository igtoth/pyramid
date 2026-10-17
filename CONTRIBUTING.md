# Contributing

Thanks for helping. Bug reports with the steps and a screenshot, new reports,
fixes and translations of the docs are all welcome.

## Layout

```
src/pyramid/
  catalog.json   every report: API path, paging, columns (the single source)
  catalog.py     loads it
  client.py      REST client: auth, retries, 429, paging (standard library + certifi)
  fetch.py       one report: listings, objects, composite reports (users + queues/roles)
  data.py        records -> rows -> CSV / JSON
  config.py      saved clients and settings (pyramid.cfg)
  gui.py         the desktop app (Tkinter)
  webserver.py   pyramid web: the page + a local proxy that adds the token
  __main__.py    command line
  web/           the web page: core.js (same rules as data.py/fetch.py), app.js, app.css
tests/           pytest, against tests/fake_genesys.py (a made-up org)
scripts/         icons, screenshots + desktop end-to-end, web end-to-end, builds, SDK fixture
packaging/       Inno Setup, DMG, AppImage
old/             earlier versions, kept for history
```

## Set up

```sh
pip install -r requirements-dev.txt     # Python 3.10+; on Linux also python3-tk
pytest                                  # no credentials needed
ruff check src tests scripts
```

End to end (what CI runs):

```sh
xvfb-run python scripts/screenshots.py shots     # every report in the real window (Linux)
playwright install chromium && python scripts/web_check.py shots
```

## Add a report

1. Find the GET in the [API explorer](https://developer.genesys.cloud/devapps/api-explorer).
2. Add an entry to `src/pyramid/catalog.json`: `key`, `label`, `section`,
   `path`, `columns` (dotted JSON paths like `division.name`; a list on the way
   is joined, a dict shows its `name`), `help`. Set `"pageSize": null` when the
   endpoint takes no paging parameters, `"paging": "cursor"` when it pages by
   cursor only, `"kind": "object"` when it returns one object, `"drop"` for
   fields that hold secrets.
3. `pytest`: `test_catalog.py` checks the path and every column against
   `tests/fixtures/sdk_fields.json` (the API's models). If the endpoint is new
   to the fixture, regenerate it: `pip install PureCloudPlatformClientV2 &&
   python scripts/sdk_fields.py`.
4. The fake org serves new listings by itself; give it real-looking data in
   `tests/fake_genesys.py` if the report deserves a screenshot.

The web page reads the same catalog: no JavaScript to write for a plain report.
A report that joins data (like users with queues) needs the same function in
`fetch.py` and `web/core.js`; `tests/test_web_parity.py` checks they agree.

## Rules

- Pyramid only reads. No request other than GET, anywhere.
- No real org data in the repository: tests, fixtures and screenshots use the
  made-up org of `tests/fake_genesys.py`.
- Never log or export a secret (`drop` in the catalog, `repr` of the client).
- The window never blocks: API calls go through `App.run_task`.

## Releases

Push a tag `vX.Y.Z` (with its section in `docs/CHANGELOG.md`), or run the
`build` workflow by hand with a version. CI builds, tests and publishes the
release; every push to `main` refreshes the nightly pre-release and the web
version.
