"""Turning API JSON into table rows and files. The web page implements the
same rules in JavaScript (web/app.js); tests/web keeps the two in step."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from typing import Any

from .catalog import Column

LIST_SEP = "; "
# A cell that starts with one of these is run as a formula by Excel and
# LibreOffice (CSV injection); exported cells get a leading apostrophe.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def resolve(obj: Any, path: str) -> Any:
    """Follow a dotted path; a list along the way is mapped over."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = [resolve(x, part) for x in cur]
            cur = [x for x in cur if x not in (None, "", [], {})]
            continue
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def cell(value: Any) -> str:
    """One display/CSV value: dicts show their name, lists are joined."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for k in ("name", "displayName", "id"):
            if isinstance(value.get(k), (str, int)):
                return str(value[k])
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) if value else ""
    if isinstance(value, (list, tuple)):
        return LIST_SEP.join(s for s in (cell(v) for v in value) if s)
    return str(value)


def rows(records: Iterable[dict[str, Any]], columns: Sequence[Column]) -> list[list[str]]:
    return [[cell(resolve(r, c.path)) for c in columns] for r in records]


def headers(columns: Sequence[Column]) -> list[str]:
    return [c.header for c in columns]


def table_columns(columns: Sequence[Column], records: Sequence[dict[str, Any]]) -> list[Column]:
    """The catalog columns, plus 'ID' when the records have one."""
    cols = list(columns)
    if records and any("id" in r for r in records[:50]) and not any(c.path == "id" for c in cols):
        cols.append(Column("ID", "id"))
    return cols


def flatten_object(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Key/value pairs of a nested object, for the settings views and their CSV."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k in sorted(obj):
            if k == "selfUri":
                continue
            key = f"{prefix}.{k}" if prefix else k
            v = obj[k]
            if isinstance(v, dict) and v:
                out.extend(flatten_object(v, key))
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                for i, x in enumerate(v):
                    out.extend(flatten_object(x, f"{key}[{i}]"))
            else:
                out.append((key, cell(v)))
    else:
        out.append((prefix or "value", cell(obj)))
    return out


def csv_safe(value: str) -> str:
    return "'" + value if value.startswith(FORMULA_START) else value


def write_csv(path: str, header: Sequence[str], body: Iterable[Sequence[str]]) -> int:
    """Write UTF-8 CSV with a BOM (Excel reads the accents right). Returns the row count."""
    n = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([csv_safe(h) for h in header])
        for r in body:
            w.writerow([csv_safe(v) for v in r])
            n += 1
    return n


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def strip_fields(records: list[dict[str, Any]], fields: Sequence[str]) -> None:
    """Remove secret-bearing fields everywhere (raw JSON export included)."""
    if not fields:
        return
    for r in records:
        for f in fields:
            r.pop(f, None)
