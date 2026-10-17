"""The catalog against the API definition (fixtures/sdk_fields.json, made by
scripts/sdk_fields.py from the official SDK): every path exists and every
column names a real field, so nothing silently comes out empty."""

import json
from pathlib import Path

import pytest

from pyramid.catalog import header_for, load

FIELDS = json.loads((Path(__file__).parent / "fixtures" / "sdk_fields.json").read_text(encoding="utf-8"))
ADDED = {"queues", "roles", "profileName"}  # added by the composite reports
SPECIAL_MODEL = {"users_queues": "/api/v2/users", "users_roles": "/api/v2/users",
                 "profile_metrics": "/api/v2/gamification/profiles/{profileId}/metrics"}

CAT = load()


def test_catalog_shape():
    assert len(CAT) >= 50
    ids = {s.id for s in CAT.sections}
    assert all(e.section in ids for e in CAT.endpoints)
    assert all(CAT.in_section(s) for s in ids), "empty section"
    for e in CAT.endpoints:
        assert e.path or e.special, e.key
        assert e.help, e.key
        assert e.is_object or e.columns, e.key


@pytest.mark.parametrize("ep", [e for e in CAT.endpoints if e.path], ids=lambda e: e.key)
def test_path_exists_in_api(ep):
    assert ep.path in FIELDS, f"{ep.path} is not a GET of the API (SDK {FIELDS['_sdk_version']})"
    assert FIELDS[ep.path]["kind"] == ("object" if ep.is_object else "list"), ep.key


@pytest.mark.parametrize("ep", [e for e in CAT.endpoints if e.columns], ids=lambda e: e.key)
def test_columns_are_api_fields(ep):
    tree = FIELDS[ep.path or SPECIAL_MODEL[ep.special]]["fields"]
    for col in ep.columns:
        head, *rest = col.path.split(".")
        if head in ADDED:
            continue
        assert head in tree, f"{ep.key}: '{head}' is not a field of {FIELDS[ep.path or SPECIAL_MODEL[ep.special]]['model']}"
        sub = tree[head]
        if rest and isinstance(sub, dict):  # None: a scalar or a free-form map
            assert rest[0] in sub, f"{ep.key}: '{col.path}' has no '{rest[0]}'"


def test_dropped_fields_exist():
    for e in CAT.endpoints:
        for f in e.drop:
            assert f in FIELDS[e.path]["fields"], (e.key, f)


def test_headers():
    assert header_for("dateCreated") == "Date Created"
    assert header_for("division.name") == "Division"
    assert header_for("dnis") == "DNIS"
    assert header_for("workPhone.display") == "Work Phone"
    assert header_for("userId") == "User ID"
