"""Regenerate tests/fixtures/sdk_fields.json: the JSON fields of the model
behind every GET in catalog.json, read from the official Python SDK (which
Genesys generates from the API definition). tests/test_catalog.py checks
every column path against it, so a renamed or removed API field fails the
tests instead of leaving an empty column.

    pip install PureCloudPlatformClientV2
    python scripts/sdk_fields.py
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from importlib.metadata import version
from pathlib import Path

import PureCloudPlatformClientV2 as sdk

ROOT = Path(__file__).resolve().parents[1]
EXTRA = [  # paths the composite reports read
    "/api/v2/routing/queues/{queueId}/members",
    "/api/v2/authorization/roles/{roleId}/users",
    "/api/v2/gamification/profiles/{profileId}/metrics",
]


def get_methods() -> dict[str, str]:
    """REST path -> response model, for every GET of the SDK."""
    out = {}
    for name in dir(sdk):
        cls = getattr(sdk, name)
        if not (inspect.isclass(cls) and name.endswith("Api")):
            continue
        for mname, fn in inspect.getmembers(cls, inspect.isfunction):
            if not mname.startswith("get_"):
                continue
            src = inspect.getsource(fn)
            path = re.search(r"resource_path = '([^']+)'", src)
            ret = re.search(r"response_type='(\w+)'", src)
            if path and ret:
                out[path.group(1)] = ret.group(1)
    return out


def model(name):
    """The SDK model class of that name (models set attribute_map in __init__)."""
    m = getattr(sdk.models, name, None) if name else None
    return m if inspect.isclass(m) and "attribute_map" in m.__init__.__code__.co_names else None


def tree(name: str, depth: int):
    obj = model(name)()
    out = {}
    for attr, js in obj.attribute_map.items():
        t = obj.swagger_types[attr]
        sub = re.fullmatch(r"list\[(\w+)\]|(\w+)", t)
        sub = sub and (sub.group(1) or sub.group(2))
        out[js] = tree(sub, depth - 1) if depth > 1 and sub and model(sub) else None
    return out


def main() -> None:
    catalog = json.loads((ROOT / "src/pyramid/catalog.json").read_text(encoding="utf-8"))
    wanted = sorted({e["path"] for e in catalog["endpoints"] if e.get("path")} | set(EXTRA) | {"/api/v2/users"})
    gets = get_methods()
    result, missing = {}, []
    for path in wanted:
        ret = gets.get(path)
        if not ret or not model(ret):
            missing.append(path)
            continue
        listing = model(ret)()
        if "entities" in listing.attribute_map:
            ent = re.search(r"list\[(\w+)\]", listing.swagger_types["entities"]).group(1)
            result[path] = {"kind": "list", "model": ent, "fields": tree(ent, 2)}
        else:
            result[path] = {"kind": "object", "model": ret, "fields": tree(ret, 2)}
    result["_sdk_version"] = version("PureCloudPlatformClientV2")
    out = ROOT / "tests/fixtures/sdk_fields.json"
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(result) - 1} paths from SDK {result['_sdk_version']} -> {out}")
    if missing:
        sys.exit(f"No GET in the SDK for: {', '.join(missing)}")


if __name__ == "__main__":
    main()
