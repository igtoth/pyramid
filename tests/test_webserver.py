import http.client
import threading

import pytest

import fake_genesys as fg
from pyramid.config import OAuthClient, Store
from pyramid.webserver import _web_file, make_server


@pytest.fixture
def local(fake, cfgdir):
    store = Store()
    store.put_client(OAuthClient("Lumen Harbor", "eu_west_1", fg.CLIENT_ID, fg.CLIENT_SECRET))
    srv = make_server(8800, store)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def req(srv, path, method="GET", host=None, cookie=True):
    port = srv.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if cookie:
        headers["Cookie"] = f"{srv.cookie}={srv.key}"
    c.request(method, path, headers=headers)
    r = c.getresponse()
    return r.status, r.getheaders(), r.read()


def test_static_page_is_marked_local(local):
    status, _, body = req(local, "/", cookie=False)
    assert status == 200 and b'data-mode="local"' in body


def test_key_in_url_sets_cookie_once(local):
    url_key = local.url_key
    assert req(local, "/?k=wrong", cookie=False)[0] == 403
    status, headers, _ = req(local, f"/?k={url_key}", cookie=False)
    assert status == 303
    cookie = dict(headers)["Set-Cookie"]
    port = local.server_address[1]
    assert cookie.startswith(f"pyramid_session_{port}={local.key};")  # named after the port
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert local.key != url_key
    assert req(local, f"/?k={url_key}", cookie=False)[0] == 403  # single use


def test_cookie_of_another_port_is_ignored(local):
    port = local.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/local/info", headers={"Host": f"127.0.0.1:{port}", "Cookie": f"pyramid_session_1={local.key}"})
    assert c.getresponse().status == 401


def test_local_needs_cookie_and_host(local):
    assert req(local, "/local/info", cookie=False)[0] == 401
    assert req(local, "/local/info", host="evil.example:80")[0] == 403
    status, _, body = req(local, "/local/info")
    assert status == 200 and b"Lumen Harbor" in body and fg.CLIENT_SECRET.encode() not in body


def test_proxy_forwards_gets_only(local):
    status, _, body = req(local, "/local/api/Lumen%20Harbor/api/v2/organizations/me")
    assert status == 200 and b"Lumen Harbor Telecom" in body
    assert req(local, "/local/api/Lumen%20Harbor/api/v2/organizations/me", method="POST")[0] == 405
    assert req(local, "/local/api/Lumen%20Harbor/oauth/token")[0] == 400
    assert req(local, "/local/api/Nobody/api/v2/users")[0] == 404


def test_proxy_keeps_paging_relative(local):
    status, _, body = req(local, "/local/api/Lumen%20Harbor/api/v2/teams?pageSize=2")
    assert status == 200 and b'"nextUri": "/api/v2/teams?' in body


def test_no_path_traversal(local):
    assert req(local, "/../config.py")[0] == 404
    assert req(local, "/..%2F__init__.py")[0] == 404
    assert req(local, "/C:/Users/x/AppData/Roaming/Pyramid/pyramid.cfg")[0] == 404
    for name in ("C:/Windows/win.ini", "/etc/passwd", "web/../config.py", "assets/pyramid-16.png", "../catalog.py"):
        assert _web_file("/" + name) is None, name
    for name in ("index.html", "app.js", "core.js", "app.css", "catalog.json", "favicon.png"):
        assert _web_file("/" + name), name


def test_encoded_dots_not_forwarded(local, fake):
    for path in ("/api/v2/%2e%2e/%2e%2e/oauth/x", "/api/v2/users/%2fx", "/api/v2/./users", "/api/v2/users/../../x"):
        assert req(local, "/local/api/Lumen%20Harbor" + path)[0] == 400, path


def test_edited_secret_takes_effect(local, fake):
    assert req(local, "/local/api/Lumen%20Harbor/api/v2/organizations/me")[0] == 200
    store = Store()
    store.put_client(OAuthClient("Lumen Harbor", "eu_west_1", fg.CLIENT_ID, "rotated-wrong"))
    assert req(local, "/local/api/Lumen%20Harbor/api/v2/organizations/me")[0] in (400, 401)


def test_unknown_region_is_a_clean_error(local, monkeypatch):
    monkeypatch.delenv("PYRAMID_API_BASE")  # the fake answers for every region otherwise
    store = Store()
    store.put_client(OAuthClient("Mars", "mars_north_1", fg.CLIENT_ID, fg.CLIENT_SECRET))
    status, _, body = req(local, "/local/api/Mars/api/v2/users")
    assert status == 400 and b"Unknown region" in body


def test_concurrent_requests_see_the_clients(local):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(16) as pool:
        codes = list(pool.map(lambda _: req(local, "/local/info")[0], range(200)))
    assert set(codes) == {200}


def post(srv, path, body, headers=None, cookie=True):
    import json
    port = srv.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json", "X-Pyramid": "1",
         "Origin": f"http://127.0.0.1:{port}"}
    if cookie:
        h["Cookie"] = f"{srv.cookie}={srv.key}"
    h.update(headers or {})
    h = {k: v for k, v in h.items() if v is not None}
    c.request("POST", path, body=json.dumps(body), headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


NEW = {"name": "Lab", "region": "eu_west_1", "clientId": fg.CLIENT_ID, "secret": fg.CLIENT_SECRET}


def test_page_adds_edits_and_deletes_clients(local):
    status, info = post(local, "/local/clients", NEW)
    assert status == 200 and [c["name"] for c in info["clients"]] == ["Lab", "Lumen Harbor"]
    assert fg.CLIENT_SECRET not in str(info)  # never sent back
    assert all(c["hasSecret"] for c in info["clients"])
    assert Store().client("Lab").client_secret == fg.CLIENT_SECRET  # same pyramid.cfg as the desktop
    # rename with an empty secret keeps the saved one
    status, info = post(local, "/local/clients", {**NEW, "name": "Lab 2", "secret": "", "oldName": "Lab"})
    assert status == 200 and Store().client("Lab 2").client_secret == fg.CLIENT_SECRET and not Store().client("Lab")
    # a new name cannot take an existing one
    assert post(local, "/local/clients", {**NEW, "name": "Lumen Harbor"})[0] == 400
    status, info = post(local, "/local/clients/delete", {"name": "Lab 2"})
    assert status == 200 and [c["name"] for c in info["clients"]] == ["Lumen Harbor"]


def test_client_form_is_checked(local):
    assert post(local, "/local/clients", {**NEW, "clientId": "nope"})[0] == 400
    assert post(local, "/local/clients", {**NEW, "region": "mars_1"})[0] == 400
    assert post(local, "/local/clients", {**NEW, "name": "a[b]"})[0] == 400
    assert post(local, "/local/clients", {**NEW, "secret": ""})[0] == 400  # new client, no secret


def test_test_connection(local):
    status, body = post(local, "/local/test", NEW)
    assert status == 200 and body["org"] == "Lumen Harbor Telecom" and body["expiresIn"] > 0
    status, body = post(local, "/local/test", {**NEW, "secret": "wrong"})
    assert status in (400, 401) and body["message"]


def test_post_needs_session_header_and_origin(local):
    assert post(local, "/local/clients", NEW, cookie=False)[0] == 401
    assert post(local, "/local/clients", NEW, headers={"X-Pyramid": None})[0] == 403
    assert post(local, "/local/clients", NEW, headers={"Origin": "https://evil.example"})[0] == 403
    assert post(local, "/local/clients", NEW, headers={"Content-Type": "text/plain"})[0] == 403
    assert post(local, "/local/elsewhere", NEW)[0] == 405
    assert not Store().client("Lab")
