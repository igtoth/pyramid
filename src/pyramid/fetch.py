"""Fetching one catalog endpoint: plain listings, objects and the few
composite reports (users with their queues, metrics of every profile)."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

from .catalog import Endpoint
from .client import CancelToken, GenesysClient, ProgressFn
from .data import strip_fields


@dataclass
class Result:
    endpoint: Endpoint
    records: list[dict[str, Any]] = field(default_factory=list)  # list endpoints
    obj: Any = None                                             # object endpoints
    raw: Any = None                                             # what "Raw JSON" saves
    fetched_at: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))
    calls: int = 0

    @property
    def count(self) -> int:
        return 1 if self.endpoint.is_object else len(self.records)


def fetch(client: GenesysClient, ep: Endpoint, cancel: CancelToken | None = None,
          progress: ProgressFn | None = None) -> Result:
    start_calls = client.calls
    if ep.special == "users_queues":
        res = _users_queues(client, ep, cancel, progress)
    elif ep.special == "users_roles":
        res = _users_roles(client, ep, cancel, progress)
    elif ep.special == "profile_metrics":
        res = _profile_metrics(client, ep, cancel, progress)
    elif ep.is_object:
        obj = client.get(ep.path, ep.query or None, cancel, progress)
        res = Result(ep, obj=obj, raw=obj)
    else:
        records, raw = [], []
        for variant in (ep.variants or ({},)):
            recs, pages = client.entities(
                ep.path, params={**ep.query, **variant}, page_size=ep.page_size,
                size_param=ep.size_param, cursor=ep.cursor, cancel=cancel, progress=progress,
                label=_label(ep, variant))
            records.extend(recs)
            raw.extend(pages)
        res = Result(ep, records=records, raw=raw)
    if ep.drop:
        strip_fields(res.records, ep.drop)
    res.calls = client.calls - start_calls
    return res


def _label(ep: Endpoint, variant: dict[str, Any]) -> str:
    extra = ", ".join(f"{v}" for v in variant.values())
    return f"{ep.label} ({extra})" if extra else ep.label


def queue_members(client: GenesysClient, queue_id: str, cancel: CancelToken | None = None,
                  progress: ProgressFn | None = None) -> list[dict[str, Any]]:
    members, _ = client.entities(f"/api/v2/routing/queues/{queue_id}/members", page_size=100,
                                 cancel=cancel, progress=progress, label="Members")
    return members


def _all_users(client: GenesysClient, cancel, progress, expand: list[str] | None = None):
    users, raw = [], []
    for state in ("active", "inactive"):
        params: dict[str, Any] = {"state": state, "sortOrder": "ASC"}
        if expand:
            params["expand"] = expand
        recs, pages = client.entities("/api/v2/users", params=params, page_size=500,
                                      cancel=cancel, progress=progress, label=f"Users ({state})")
        users.extend(recs)
        raw.extend(pages)
    return users, raw


def _users_roles(client: GenesysClient, ep: Endpoint, cancel, progress) -> Result:
    """Users with their roles, from one user list per role (far fewer calls
    than one authorization lookup per user)."""
    users, raw_users = _all_users(client, cancel, progress)
    roles, _ = client.entities("/api/v2/authorization/roles", page_size=100, cancel=cancel,
                               progress=progress, label="Roles")
    by_user: dict[str, list[str]] = {}
    for i, r in enumerate(roles, 1):
        if progress:
            progress(f"Role members {i}/{len(roles)}: {r.get('name', '')}")
        members, _ = client.entities(f"/api/v2/authorization/roles/{r['id']}/users", page_size=100,
                                     cancel=cancel)
        for m in members:
            if m.get("id"):
                by_user.setdefault(m["id"], []).append(r.get("name", r["id"]))
    for u in users:
        u["roles"] = sorted(by_user.get(u.get("id"), []), key=str.lower)
    return Result(ep, records=users, raw={"users": raw_users, "roles": roles})


def _users_queues(client: GenesysClient, ep: Endpoint, cancel, progress) -> Result:
    """Users with their queues, from one member list per queue.

    Asking every user for their queues costs one call per user and runs
    into the rate limit in large orgs; there are far fewer queues than
    users, so the membership is read queue by queue and turned around.
    """
    users, raw_users = _all_users(client, cancel, progress, expand=["skills"])
    queues, _ = client.entities("/api/v2/routing/queues", page_size=100, cancel=cancel,
                                progress=progress, label="Queues")
    by_user: dict[str, list[str]] = {}
    for i, q in enumerate(queues, 1):
        if progress:
            progress(f"Queue members {i}/{len(queues)}: {q.get('name', '')}")
        for m in queue_members(client, q["id"], cancel):
            uid = m.get("id") or (m.get("user") or {}).get("id")
            if uid:
                by_user.setdefault(uid, []).append(q.get("name", q["id"]))
    for u in users:
        u["queues"] = sorted(by_user.get(u.get("id"), []), key=str.lower)
    return Result(ep, records=users, raw={"users": raw_users, "queues": queues})


def _profile_metrics(client: GenesysClient, ep: Endpoint, cancel, progress) -> Result:
    profiles = client.get("/api/v2/gamification/profiles", None, cancel, progress).get("entities") or []
    records, raw = [], []
    for i, p in enumerate(profiles, 1):
        if progress:
            progress(f"Profile {i}/{len(profiles)}: {p.get('name', '')}")
        data = client.get(f"/api/v2/gamification/profiles/{p['id']}/metrics", None, cancel, progress)
        raw.append({"profile": p, "metrics": data})
        for m in data.get("entities") or []:
            m["profileName"] = p.get("name")
            records.append(m)
    return Result(ep, records=records, raw=raw)
