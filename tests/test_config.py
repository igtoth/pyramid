import os
import stat

import pytest

from pyramid.config import OAuthClient, Store, valid_proxy


def test_v2_file_is_migrated(cfgdir):
    (cfgdir / "pyramid.cfg").write_text(
        "[clients]\nprod org = eu_west_1,11111111-2222-4333-8444-555555555555,se%cr,et\n\n"
        "[settings]\ntheme = dark\nproxy_url = http://u:p%40ss@proxy:8080\nproxy_enabled = 1\n\n"
        "[Settings]\nterms_accepted = 1\n", encoding="utf-8")
    s = Store()
    c = s.client("prod org")
    assert c and c.region == "eu_west_1" and c.client_secret == "se%cr,et"  # % and , survive
    assert s.get("theme") == "dark" and s.get_bool("terms_accepted")
    assert s.proxy() == "http://u:p%40ss@proxy:8080"
    s.save()
    text = (cfgdir / "pyramid.cfg").read_text(encoding="utf-8")
    assert "[client:prod org]" in text and "[clients]" not in text and "[Settings]" not in text


def test_names_keep_their_case_and_rename(cfgdir):
    s = Store()
    s.put_client(OAuthClient("Prod Org", "us_east_1", "id", "sec"))
    s.put_client(OAuthClient("prod org", "us_east_1", "id2", "sec2"))
    assert [c.name for c in Store().clients()] == ["Prod Org", "prod org"]
    s.put_client(OAuthClient("Production", "us_east_1", "id", "sec"), old_name="Prod Org")
    assert [c.name for c in Store().clients()] == ["prod org", "Production"]
    s.delete_client("prod org")
    assert [c.name for c in Store().clients()] == ["Production"]


def test_bad_names_rejected(cfgdir):
    with pytest.raises(ValueError):
        Store().put_client(OAuthClient("bad]name", "us_east_1", "i", "s"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_file_is_private(cfgdir):
    s = Store()
    s.put_client(OAuthClient("x", "us_east_1", "i", "s"))
    assert stat.S_IMODE(os.stat(s.path).st_mode) == 0o600


def test_proxy_validation():
    assert valid_proxy("") and valid_proxy("http://p:8080") and valid_proxy("https://p")
    assert not valid_proxy("socks5://p") and not valid_proxy("proxy:8080")
