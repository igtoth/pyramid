import threading
import time

import pytest

import fake_genesys as fg
from pyramid.catalog import load
from pyramid.client import ApiError, Cancelled, CancelToken, GenesysClient
from pyramid.fetch import fetch

CAT = load()


def test_bad_credentials(fake):
    c = GenesysClient("us_east_1", fg.CLIENT_ID, "wrong")
    with pytest.raises(ApiError) as e:
        c.token()
    assert e.value.status == 400 and "Invalid client credentials" in str(e.value)


def test_secret_not_in_repr(client):
    assert fg.CLIENT_SECRET not in repr(client)


def test_page_number_paging(client):
    users, raw = client.entities("/api/v2/users", params={"state": "active"}, page_size=25)
    assert len(raw) == 3 and len(users) == len({u["id"] for u in users}) > 50


def test_cursor_paging(client, fake):
    teams = fake.handler.org.listings["/api/v2/teams"]
    recs, raw = client.entities("/api/v2/teams", page_size=5, cursor=True)
    assert len(recs) == len(teams) and len(raw) == -(-len(teams) // 5)


def test_rate_limit_retry_honours_retry_after(client, fake):
    fake.handler.fail_429["/api/v2/routing/skills"] = 2
    seen = []
    t0 = time.time()
    recs, _ = client.entities("/api/v2/routing/skills", progress=seen.append)
    assert recs and time.time() - t0 >= 2.0  # Retry-After: 1, twice
    assert sum("HTTP 429" in s for s in seen) == 2


def test_cancel_during_rate_limit_wait(client, fake):
    fake.handler.fail_429["/api/v2/routing/languages"] = 50
    cancel = CancelToken()
    threading.Timer(0.3, cancel.cancel).start()
    t0 = time.time()
    with pytest.raises(Cancelled):
        client.entities("/api/v2/routing/languages", cancel=cancel)
    assert time.time() - t0 < 1.5


def test_errors_raise_with_correlation_id(client, fake):
    fake.handler.fail_status["/api/v2/oauth/clients"] = 403
    with pytest.raises(ApiError) as e:
        fetch(client, CAT["oauth_clients"])
    assert e.value.status == 403 and e.value.correlation_id == "corr-123"


def test_expired_token_is_refreshed(client):
    client.token()
    client._token = "stale"  # the API answers 401; the client gets a new token once
    assert client.get("/api/v2/organizations/me")["name"] == "Lumen Harbor Telecom"


def test_every_report_fetches(client):
    for ep in CAT.endpoints:
        res = fetch(client, ep)
        assert res.count > 0, ep.key


def test_users_include_inactive(client):
    res = fetch(client, CAT["users"])
    states = {u["state"] for u in res.records}
    assert states == {"active", "inactive"}


def test_users_queues_turned_around(client, fake):
    res = fetch(client, CAT["usersqueues"])
    org = fake.handler.org
    q = org.queues[0]
    member = q["_members"][0]
    row = next(u for u in res.records if u["id"] == member["id"])
    assert q["name"] in row["queues"]
    # one call per queue, not per user
    assert res.calls < len(org.users) / 2


def test_users_roles(client, fake):
    res = fetch(client, CAT["usersroles"])
    admin = next(r for r in fake.handler.org.roles if r["name"] == "admin")
    for u in admin["_users"]:
        assert "admin" in next(x for x in res.records if x["id"] == u["id"])["roles"]


def test_secrets_dropped_everywhere(client):
    for key in ("oauth_clients", "recording_keys"):
        res = fetch(client, CAT[key])
        assert "SHOULD-NEVER-APPEAR" not in repr(res.records) + repr(res.raw), key


def test_proxy_setting_is_used(fake, monkeypatch):
    for v in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(v, raising=False)
    c = GenesysClient("us_east_1", fg.CLIENT_ID, fg.CLIENT_SECRET, proxy="http://127.0.0.1:9", max_retries=0)
    with pytest.raises(ApiError):
        c.token()  # the dead proxy is really in the way


def test_page_count_without_page_number_is_not_walked(client, monkeypatch):
    """A listing fetched without pageNumber must not refetch the same page pageCount times."""
    calls = []

    def fake_get(path, params=None, cancel=None, progress=None):
        calls.append((path, params))
        return {"entities": [{"id": "a"}], "pageCount": 3}

    monkeypatch.setattr(client, "get", fake_get)
    recs, _ = client.entities("/api/v2/oauth/clients", page_size=None)
    assert len(calls) == 1 and len(recs) == 1
    calls.clear()
    recs, _ = client.entities("/api/v2/teams", page_size=10, cursor=True)
    assert len(calls) == 1


def test_retry_after_forms():
    import email.utils
    import time as _t
    import urllib.error

    from pyramid.client import _retry_after

    def err(v):
        return urllib.error.HTTPError("u", 429, "x", {"Retry-After": v} if v else {}, None)

    assert _retry_after(err("3")) == 3
    assert _retry_after(err("0")) == 1
    assert _retry_after(err("99999")) == 120
    assert 25 <= _retry_after(err(email.utils.formatdate(_t.time() + 30, usegmt=True))) <= 31
    assert _retry_after(err("soon")) is None and _retry_after(err(None)) is None
