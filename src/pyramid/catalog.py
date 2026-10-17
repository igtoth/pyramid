"""The endpoint catalog: one entry per button, shared by the desktop app,
the command line and the web page (catalog.json is the single source)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

DEFAULT_PAGE_SIZE = 100
ACRONYMS = {"id": "ID", "dnis": "DNIS", "url": "URL", "uri": "URI", "api": "API", "mx": "MX", "kpi": "KPI",
            "dnc": "DNC", "smtp": "SMTP", "rrule": "RRule"}


@dataclass(frozen=True)
class Column:
    header: str
    path: str


@dataclass(frozen=True)
class Section:
    id: str
    name: str
    icon: str
    color: int


@dataclass(frozen=True)
class Endpoint:
    key: str
    label: str
    section: str
    help: str = ""
    path: str | None = None
    kind: str = "list"              # "list" or "object"
    page_size: int | None = DEFAULT_PAGE_SIZE
    size_param: str = "pageSize"
    cursor: bool = False            # paged by nextUri only (no pageNumber)
    query: dict[str, Any] = field(default_factory=dict)
    variants: tuple[dict[str, Any], ...] = ()
    columns: tuple[Column, ...] = ()
    drop: tuple[str, ...] = ()
    special: str | None = None
    actions: tuple[str, ...] = ()
    slow: bool = False

    @property
    def is_object(self) -> bool:
        return self.kind == "object"


def header_for(path: str) -> str:
    """'dateCreated' -> 'Date Created', 'division.name' -> 'Division'."""
    parts = path.split(".")
    if len(parts) > 1 and parts[-1] in ("name", "id", "display"):
        parts = parts[:-1]
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", parts[-1]).replace("_", " ").split()
    return " ".join(ACRONYMS.get(w.lower(), w if w.isupper() else w.capitalize()) for w in words)


def _column(spec: Any) -> Column:
    if isinstance(spec, str):
        return Column(header_for(spec), spec)
    header, path = spec
    return Column(header, path)


def _endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        key=raw["key"],
        label=raw["label"],
        section=raw["section"],
        help=raw.get("help", ""),
        path=raw.get("path"),
        kind=raw.get("kind", "list"),
        page_size=raw.get("pageSize", DEFAULT_PAGE_SIZE),
        size_param=raw.get("sizeParam", "pageSize"),
        cursor=raw.get("paging") == "cursor",
        query=dict(raw.get("query", {})),
        variants=tuple(raw.get("variants", ())),
        columns=tuple(_column(c) for c in raw.get("columns", ())),
        drop=tuple(raw.get("drop", ())),
        special=raw.get("special"),
        actions=tuple(raw.get("actions", ())),
        slow=bool(raw.get("slow", False)),
    )


class Catalog:
    def __init__(self, data: dict[str, Any]):
        self.sections = [Section(**s) for s in data["sections"]]
        self.endpoints = [_endpoint(e) for e in data["endpoints"]]
        self._by_key = {e.key: e for e in self.endpoints}
        if len(self._by_key) != len(self.endpoints):
            raise ValueError("duplicate endpoint keys in catalog")

    def __len__(self) -> int:
        return len(self.endpoints)

    def __getitem__(self, key: str) -> Endpoint:
        return self._by_key[key]

    def __contains__(self, key: str) -> bool:
        return key in self._by_key

    def in_section(self, section_id: str) -> list[Endpoint]:
        return [e for e in self.endpoints if e.section == section_id]


def raw_catalog() -> dict[str, Any]:
    text = resources.files("pyramid").joinpath("catalog.json").read_text(encoding="utf-8")
    return json.loads(text)


_CATALOG: Catalog | None = None


def load() -> Catalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = Catalog(raw_catalog())
    return _CATALOG
