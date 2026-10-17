import http.client
import threading

import pytest

import fake_genesys as fg
from pyramid.config import OAuthClient, Store
from pyramid.webserver import COOKIE, make_server


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
        headers["Cookie"] = f"{COOKIE}={srv.key}"
    c.request(method, path, headers=headers)
    r = c.getresponse()
    return r.status, r.getheaders(), r.read()


def test_static_page_is_marked_local(local):
    status, _, body = req(local, "/", cookie=False)
    assert status == 200 and b'data-mode="local"' in body


def test_key_in_url_sets_cookie(local):
    status, headers, _ = req(local, f"/?k={local.key}", cookie=False)
    assert status == 303
    cookie = dict(headers)["Set-Cookie"]
    assert local.key in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert req(local, "/?k=wrong", cookie=False)[0] == 403


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
