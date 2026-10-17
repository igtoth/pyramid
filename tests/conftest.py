import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import fake_genesys as fg  # noqa: E402


@pytest.fixture(scope="session")
def fake():
    srv, url = fg.serve()
    os.environ["PYRAMID_API_BASE"] = url
    os.environ["PYRAMID_LOGIN_BASE"] = url
    yield srv
    srv.shutdown()


@pytest.fixture(autouse=True)
def _clean_faults(request):
    yield
    if "fake" in request.fixturenames:
        srv = request.getfixturevalue("fake")
        srv.handler.fail_429.clear()
        srv.handler.fail_status.clear()


@pytest.fixture
def client(fake):
    from pyramid.client import GenesysClient

    return GenesysClient("us_east_1", fg.CLIENT_ID, fg.CLIENT_SECRET, backoff_cap=0.2)


@pytest.fixture
def cfgdir(tmp_path, monkeypatch):
    monkeypatch.setenv("PYRAMID_CONFIG_DIR", str(tmp_path))
    return tmp_path
