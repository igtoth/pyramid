"""A fake Genesys Cloud for tests, demos and screenshots.

Serves /oauth/token and every GET in catalog.json with a made-up org
("Lumen Harbor Telecom"); no real data anywhere. Page-number listings
honour pageSize/pageNumber, cursor listings hand out nextUri.

Run it on its own:  python tests/fake_genesys.py --port 8765
then point Pyramid at it:
  PYRAMID_API_BASE=http://127.0.0.1:8765 PYRAMID_LOGIN_BASE=http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import re
import sys
import threading
import unicodedata
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pyramid.catalog import load  # noqa: E402

CLIENT_ID = "11111111-2222-4333-8444-555555555555"
CLIENT_SECRET = "fake-secret"
DOMAIN = "lumenharbor.example"

FIRST = ["Ana", "Bruno", "Carla", "Diego", "Elena", "Felipe", "Giulia", "Hugo", "Inês", "João", "Kenji",
         "Laura", "Marco", "Nadia", "Otto", "Paula", "Rafael", "Sofia", "Tomás", "Vera", "Yuki", "Zoe",
         "Mateus", "Lívia", "Omar", "Priya", "Lucas", "Mila", "Theo", "Clara"]
LAST = ["Almeida", "Berg", "Costa", "Duarte", "Engel", "Ferreira", "Gomes", "Horvat", "Ito", "Jensen",
        "Kowalski", "Lima", "Moreau", "Novak", "Oliveira", "Pereira", "Rossi", "Silva", "Tanaka", "Weber"]
DIVISIONS = [{"id": "d-home", "name": "Home"}, {"id": "d-emea", "name": "EMEA"}, {"id": "d-amer", "name": "Americas"}]
QUEUES = ["Billing", "Technical Support", "Sales Inbound", "Retention", "Fiber Install", "VIP Care",
          "Mobile Support", "Spanish Line", "Callbacks", "Email Care"]
SKILLS = ["Billing", "Fiber", "Mobile", "Retention", "Escalations", "Spanish", "German", "Chat"]
ROLES = ["admin", "Supervisor", "Agent", "Quality Evaluator", "Reporting Viewer", "Telephony Admin", "Developer"]
FLOWS = [("Main Inbound", "inboundcall"), ("After Hours", "inboundcall"), ("Billing IVR", "inboundcall"),
         ("Support Chat", "inboundchat"), ("Hold Music", "inqueuecall"), ("Email Router", "inboundemail"),
         ("Survey Bot", "bot"), ("Callback Workflow", "workflow"), ("Secure Payment", "securecall"),
         ("WhatsApp Entry", "inboundshortmessage"), ("Outbound Dialer", "outboundcall"), ("VIP Greeting", "inboundcall")]


def _iso(rng: random.Random, year: int = 2026) -> str:
    return f"{year}-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}T{rng.randint(6, 20):02d}:{rng.randint(0, 59):02d}:00.000Z"


def _id(rng: random.Random) -> str:
    h = f"{rng.getrandbits(128):032x}"
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


class Org:
    """Deterministic made-up data."""

    def __init__(self, seed: int = 7, users: int = 64):
        rng = random.Random(seed)
        self.rng = rng
        self.skills = [{"id": _id(rng), "name": s, "state": "active", "dateModified": _iso(rng)} for s in SKILLS]
        self.users = []
        for i in range(users):
            fn, ln = FIRST[i % len(FIRST)], LAST[(i * 7 + i // len(FIRST)) % len(LAST)]
            plain = unicodedata.normalize("NFKD", f"{fn}.{ln}").encode("ascii", "ignore").decode().lower()
            u = {"id": _id(rng), "name": f"{fn} {ln}", "username": f"{plain}@{DOMAIN}",
                 "email": "", "title": rng.choice(["Agent", "Senior Agent", "Team Lead", "Supervisor", "Analyst"]),
                 "department": rng.choice(["Care", "Sales", "Network Ops", "Quality"]),
                 "division": rng.choice(DIVISIONS), "state": "inactive" if i % 11 == 10 else "active",
                 "lastTokenIssued": {"dateIssued": _iso(rng)}, "dateLastLogin": _iso(rng),
                 "skills": [{"id": s["id"], "name": s["name"], "proficiency": rng.randint(1, 5)}
                            for s in rng.sample(self.skills, rng.randint(1, 3))],
                 "selfUri": "/api/v2/users/x"}
            u["email"] = u["username"]
            self.users.append(u)
        self.queues = []
        for q in QUEUES:
            members = rng.sample([u for u in self.users if u["state"] == "active"], rng.randint(4, 18))
            self.queues.append({"id": _id(rng), "name": q, "division": rng.choice(DIVISIONS),
                                "memberCount": len(members), "joinedMemberCount": rng.randint(1, len(members)),
                                "scoringMethod": "TimestampAndPriority", "skillEvaluationMethod": rng.choice(["ALL", "BEST", "NONE"]),
                                "dateCreated": _iso(rng, 2024), "description": f"{q} queue",
                                "_members": members})
        self.roles = []
        for r in ROLES:
            holders = rng.sample(self.users, {"admin": 3, "Agent": 40}.get(r, rng.randint(2, 9)))
            self.roles.append({"id": _id(rng), "name": r, "description": f"{r} role", "userCount": len(holders),
                               "default": r in ("admin", "Agent"), "base": False, "_users": holders})
        self.flows = [{"id": _id(rng), "name": n, "type": t, "division": DIVISIONS[0], "active": True,
                       "publishedVersion": {"id": _id(rng), "name": f"{rng.randint(3, 40)}.0"},
                       "description": ""} for n, t in FLOWS]
        self.objects = {
            "/api/v2/organizations/me": {"id": _id(rng), "name": "Lumen Harbor Telecom", "domain": "lumenharbor",
                                         "defaultLanguage": "en-us", "defaultCountryCode": "US", "state": "active",
                                         "voicemailEnabled": True, "productPlatform": "GenesysCloud",
                                         "features": {"realtimeCIC": False, "purecloud": True, "hipaa": False,
                                                      "ucEnabled": True, "pci": True, "purecloudVoice": True}},
            "/api/v2/routing/utilization": {"utilization": {"call": {"maximumCapacity": 1, "includeNonAcd": True},
                                                            "chat": {"maximumCapacity": 3, "interruptableMediaTypes": ["call"]},
                                                            "email": {"maximumCapacity": 2},
                                                            "message": {"maximumCapacity": 4}}},
            "/api/v2/recording/settings": {"maxSimultaneousStreams": 10, "maxConfigurableScreenRecordingStreams": 2,
                                           "regionalRecordingStorageEnabled": True, "recordingPlaybackUrlTtl": 60,
                                           "recordingBatchDownloadUrlTtl": 60},
        }
        self.listings: dict[str, list[dict]] = {}
        self._build_listings()

    def _generic(self, label: str, columns, n: int) -> list[dict]:
        rng = self.rng
        out = []
        for i in range(1, n + 1):
            e: dict = {"id": _id(rng)}
            for c in columns:
                parts = c.path.split(".")
                cur = e
                for p in parts[:-1]:
                    cur = cur.setdefault(p, {})
                cur[parts[-1]] = self._value(parts[-1], label, i)
            out.append(e)
        return out

    def _value(self, field: str, label: str, i: int):
        rng = self.rng
        f = field.lower()
        if f == "name":
            return f"{label.rstrip('s')} {i:02d}"
        if f.startswith("date") or f.endswith("date") or f.endswith("datetime") or f in ("start", "end"):
            return _iso(rng)
        if f in ("enabled", "active", "published", "inservice", "connected", "managed", "validated", "authorized",
                 "allowalldomains", "primary", "deactivated", "disabled", "repeat", "default", "base", "beepdetectionenabled"):
            return rng.random() > 0.25 if f not in ("deactivated", "disabled") else rng.random() > 0.85
        if "count" in f or f in ("size", "precision", "percentagecomplete", "routingtimeoutseconds", "accesstokenvalidityseconds", "version"):
            return rng.randint(1, 900)
        if f == "state":
            return "active"
        if f == "status":
            return rng.choice(["Active", "Published", "Running"])
        if f in ("dnis", "languages", "allowedDomains".lower(), "columnnames", "licenses", "roleids"):
            return [f"{field}-{rng.randint(10, 99)}" for _ in range(rng.randint(1, 3))]
        return f"{field} {i}"

    def _build_listings(self) -> None:
        rng = self.rng
        cat = load()
        L = self.listings
        L["/api/v2/users"] = self.users
        L["/api/v2/routing/queues"] = self.queues
        L["/api/v2/authorization/roles"] = self.roles
        L["/api/v2/routing/skills"] = self.skills
        L["/api/v2/flows"] = self.flows
        L["/api/v2/telephony/providers/edges"] = [
            {"id": _id(rng), "name": f"edge-{site}-{n}", "site": {"name": site}, "onlineStatus": "ONLINE",
             "statusCode": "INSERVICE", "edgeDeploymentType": "HARDWARE", "fullSoftwareVersion": "1.0.0.12345",
             "state": "active"} for site in ("porto", "frankfurt", "dallas") for n in (1, 2)]
        L["/api/v2/telephony/providers/edges/trunks"] = [
            {"id": _id(rng), "name": n, "trunkType": t, "edge": {"name": "edge-porto-1"},
             "connectedStatus": {"connected": c}, "inService": True, "enabled": True, "state": "active"}
            for n, t, c in [("BYOC Carrier A", "EXTERNAL", True), ("BYOC Carrier B", "EXTERNAL", True),
                            ("Legacy PBX", "EXTERNAL", False), ("Station Trunk", "STATION", True)]]
        L["/api/v2/architect/ivrs"] = [
            {"id": _id(rng), "name": n, "dnis": d, "openHoursFlow": {"name": o}, "closedHoursFlow": {"name": "After Hours"},
             "holidayHoursFlow": {"name": "After Hours"}, "scheduleGroup": {"name": "Care Hours"}, "division": DIVISIONS[0]}
            for n, d, o in [("Main Line", ["+15550100", "+15550101"], "Main Inbound"),
                            ("Billing", ["+15550110"], "Billing IVR"), ("VIP", ["+15550199"], "VIP Greeting")]]
        L["/api/v2/oauth/clients"] = [
            {"id": _id(rng), "name": n, "authorizedGrantType": g, "state": "active", "accessTokenValiditySeconds": 86400,
             "roleIds": [self.roles[0]["id"]], "registeredRedirectUri": [], "dateCreated": _iso(rng, 2025),
             "secret": "SHOULD-NEVER-APPEAR"}
            for n, g in [("Pyramid audit", "CLIENT-CREDENTIALS"), ("Pyramid web", "CODE"), ("CRM sync", "CLIENT-CREDENTIALS")]]
        L["/api/v2/license/users"] = [{"id": u["id"], "licenses": ["genesys-cloud-cx-3"] + (["wem-addon"] if i % 3 == 0 else [])}
                                      for i, u in enumerate(self.users)]
        L["/api/v2/gamification/profiles"] = [
            {"id": _id(rng), "name": n, "division": DIVISIONS[0], "active": True, "memberCount": rng.randint(5, 40),
             "dateCreated": _iso(rng, 2025)} for n in ("Care Agents", "Sales Agents")]
        self.profile_metrics = {
            p["id"]: [{"id": _id(rng), "name": m, "metricDefinitionId": _id(rng), "precision": 0, "dateCreated": _iso(rng)}
                      for m in ("Average handle time", "Answer rate", "Adherence")]
            for p in L["/api/v2/gamification/profiles"]}
        for ep in cat.endpoints:
            if ep.path and ep.path not in L and not ep.is_object:
                L[ep.path] = self._generic(ep.label, ep.columns, rng.randint(4, 14))
        L["/api/v2/recording/keyconfigurations"] = [
            {"id": _id(rng), "keyConfigurationType": "KmsSymmetric", "url": "https://kms.example", "apiId": "kms-1",
             "apiKey": "SHOULD-NEVER-APPEAR", "lastError": ""}]


class Handler(BaseHTTPRequestHandler):
    server_version = "FakeGenesys/1.0"
    org: Org
    fail_429: dict     # path -> how many 429s to answer first
    fail_status: dict  # path -> status to answer every time
    cors_client_credentials = True  # False: like a token endpoint that refuses browsers for this grant

    def log_message(self, *_):  # quiet
        pass

    def _json(self, code: int, body, headers=None, cors: bool = True) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):  # CORS preflight for the web page
        self._json(204, {})

    def do_POST(self):
        if self.path != "/oauth/token":
            return self._json(404, {"message": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        auth = self.headers.get("Authorization", "")
        ok = auth == "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        if form.get("grant_type") == ["authorization_code"]:
            ok = True  # PKCE in the web page
        cors = self.cors_client_credentials or form.get("grant_type") != ["client_credentials"]
        if not ok:
            return self._json(400, {"error": "invalid_client", "error_description": "Invalid client credentials"}, cors=cors)
        self._json(200, {"access_token": "fake-token", "token_type": "bearer", "expires_in": 86399}, cors=cors)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/oauth/authorize":  # PKCE: sign the user in at once and send them back
            if q.get("response_type") != "code" or q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
                return self._json(400, {"error": "invalid_request"})
            back = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "fake-code", "state": q.get("state", "")})
            self.send_response(302)
            self.send_header("Location", back)
            self.end_headers()
            return
        if self.headers.get("Authorization") != "Bearer fake-token":
            return self._json(401, {"message": "Invalid login credentials.", "code": "bad.credentials"})
        status = self.fail_status.get(u.path)
        if status:
            return self._json(status, {"message": f"Injected {status}"}, {"inin-correlation-id": "corr-123"})
        n = self.fail_429.get(u.path, 0)
        if n:
            self.fail_429[u.path] = n - 1
            return self._json(429, {"message": "Rate limit exceeded"}, {"Retry-After": "1"})
        org = self.org
        if u.path in org.objects:
            return self._json(200, org.objects[u.path])
        m = re.fullmatch(r"/api/v2/routing/queues/([^/]+)/members", u.path)
        if m:
            q_ = next((x for x in org.queues if x["id"] == m.group(1)), None)
            if not q_:
                return self._json(404, {"message": "queue not found"})
            members = [{"id": x["id"], "name": x["name"], "user": {"id": x["id"]}, "joined": True,
                        "routingStatus": {"status": "IDLE"}} for x in q_["_members"]]
            return self._page(u.path, members, q, cursor=True)
        m = re.fullmatch(r"/api/v2/authorization/roles/([^/]+)/users", u.path)
        if m:
            r = next((x for x in org.roles if x["id"] == m.group(1)), None)
            return self._page(u.path, [{"id": x["id"], "name": x["name"]} for x in r["_users"]], q)
        m = re.fullmatch(r"/api/v2/gamification/profiles/([^/]+)/metrics", u.path)
        if m:
            return self._json(200, {"entities": org.profile_metrics.get(m.group(1), []), "total": 3})
        items = org.listings.get(u.path)
        if items is None:
            return self._json(404, {"message": f"No fake for {u.path}"})
        if u.path == "/api/v2/users" and "state" in q:
            items = [x for x in items if x["state"] == q["state"]]
        items = [{k: v for k, v in x.items() if not k.startswith("_")} for x in items]
        cursor_paths = {e.path for e in load().endpoints if e.cursor}
        if u.path in cursor_paths:
            return self._page(u.path, items, q, cursor=True)
        if "pageSize" not in q and "pageNumber" not in q:
            return self._json(200, {"entities": items, "total": len(items)})
        return self._page(u.path, items, q)

    def _page(self, path, items, q, cursor=False):
        size = int(q.get("pageSize") or q.get("limit") or 25)
        if cursor:
            start = int(q.get("cursor") or q.get("after") or 0)
            chunk = items[start:start + size]
            body = {"entities": chunk}
            if start + size < len(items):
                key = "cursor" if "limit" in q else "after"
                rest = {k: v for k, v in q.items() if k not in ("cursor", "after")}
                rest[key] = start + size
                body["nextUri"] = f"{path}?{urllib.parse.urlencode(rest)}"
            return self._json(200, body)
        number = int(q.get("pageNumber") or 1)
        count = max(1, -(-len(items) // size)) if items else 0
        chunk = items[(number - 1) * size: number * size]
        return self._json(200, {"entities": chunk, "pageSize": size, "pageNumber": number,
                                "total": len(items), "pageCount": count})


def serve(port: int = 0, org: Org | None = None) -> tuple[ThreadingHTTPServer, str]:
    """Start the fake in a thread; returns (server, base_url)."""
    handler = type("H", (Handler,), {"org": org or Org(), "fail_429": {}, "fail_status": {}})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.handler = handler  # tests reach fail_429 / fail_status through it
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv, url = serve(a.port)
    print(f"Fake Genesys Cloud on {url}  (client id {CLIENT_ID}, secret {CLIENT_SECRET})", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
