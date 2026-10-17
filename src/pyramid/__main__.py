"""Command line entry point.

  pyramid                       open the desktop app
  pyramid web [--port 8710]     open the web version on this computer
  pyramid list                  list the reports
  pyramid clients               list the saved OAuth clients
  pyramid export users queues --client "Prod" -o exports/
  pyramid export all --client "Prod" -o snapshot/      every report, CSV + JSON
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

from . import APP_TITLE, __version__


def _client_from_args(args):
    from .client import GenesysClient
    from .config import Store

    store = Store()
    proxy = args.proxy or os.environ.get("GC_PROXY_URL") or store.proxy()
    if args.client:
        c = store.client(args.client)
        if not c:
            names = ", ".join(x.name for x in store.clients()) or "none saved"
            sys.exit(f"No saved client named {args.client!r} (saved: {names})")
        return GenesysClient(c.region, c.client_id, c.client_secret, proxy=proxy), c.name
    region, cid, sec = (os.environ.get(k) for k in ("GC_REGION", "GC_CLIENT_ID", "GC_CLIENT_SECRET"))
    if region and cid and sec:
        return GenesysClient(region, cid, sec, proxy=proxy), "env"
    sys.exit("Pass --client NAME (a client saved in the app) or set GC_REGION, GC_CLIENT_ID and GC_CLIENT_SECRET")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "org"


def cmd_export(args) -> int:
    from . import data
    from .catalog import load
    from .client import ApiError
    from .fetch import fetch

    cat = load()
    keys = [e.key for e in cat.endpoints] if args.reports == ["all"] else args.reports
    unknown = [k for k in keys if k not in cat]
    if unknown:
        sys.exit(f"Unknown report(s): {', '.join(unknown)}. See: pyramid list")
    client, org = _client_from_args(args)
    out = Path(args.output)
    many = len(keys) > 1 or args.output.endswith(("/", os.sep)) or out.is_dir()
    if many:
        out.mkdir(parents=True, exist_ok=True)
    formats = ["csv", "json"] if args.format == "both" else [args.format]
    failed = 0
    for key in keys:
        ep = cat[key]
        print(f"{ep.label}...", end=" ", flush=True, file=sys.stderr)
        try:
            res = fetch(client, ep, progress=None)
        except ApiError as e:
            failed += 1
            print(f"failed: {e}", file=sys.stderr)
            continue
        for fmt in formats:
            path = out / f"{_safe(org)}_{key}.{fmt}" if many else out
            if many is False and len(formats) > 1:
                path = out.with_suffix(f".{fmt}")
            if fmt == "json":
                data.write_json(str(path), res.raw)
            elif ep.is_object:
                data.write_csv(str(path), ["Key", "Value"], data.flatten_object(res.obj))
            else:
                cols = data.table_columns(ep.columns, res.records)
                data.write_csv(str(path), data.headers(cols), data.rows(res.records, cols))
        print(f"{res.count} records, {res.calls} calls", file=sys.stderr)
    return 1 if failed else 0


def cmd_list(_args) -> int:
    from .catalog import load

    cat = load()
    for s in cat.sections:
        print(f"\n{s.name}")
        for e in cat.in_section(s.id):
            print(f"  {e.key:32} {e.label}")
    print(f"\n{len(cat)} reports")
    return 0


def cmd_clients(_args) -> int:
    from .config import Store

    store = Store()
    for c in store.clients():
        print(f"{c.name}\t{c.region}\t{c.client_id[:8]}...")
    if not store.clients():
        print(f"No saved clients in {store.path}", file=sys.stderr)
    return 0


def cmd_web(args) -> int:
    from .webserver import run

    return run(port=args.port, open_browser=not args.no_browser)


def cmd_gui(_args) -> int:
    from .gui import main as gui_main

    return gui_main()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pyramid", description=f"{APP_TITLE} {__version__}")
    ap.add_argument("--version", action="version", version=f"pyramid {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every request to stderr")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the desktop app (the default)").set_defaults(fn=cmd_gui)
    w = sub.add_parser("web", help="open the web version on this computer")
    w.add_argument("--port", type=int, default=8710)
    w.add_argument("--no-browser", action="store_true")
    w.set_defaults(fn=cmd_web)
    sub.add_parser("list", help="list the reports").set_defaults(fn=cmd_list)
    sub.add_parser("clients", help="list the saved OAuth clients").set_defaults(fn=cmd_clients)
    e = sub.add_parser("export", help="export reports to CSV or JSON")
    e.add_argument("reports", nargs="+", help="report keys (see 'pyramid list'), or 'all'")
    e.add_argument("--client", help="name of a client saved in the app")
    e.add_argument("--format", choices=["csv", "json", "both"], default="csv")
    e.add_argument("-o", "--output", default="exports/", help="file, or folder for several reports")
    e.add_argument("--proxy", help="HTTP(S) proxy URL")
    e.set_defaults(fn=cmd_export)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    if not getattr(args, "fn", None):
        return cmd_gui(args)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
