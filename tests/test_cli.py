import csv
import json

import fake_genesys as fg
from pyramid.__main__ import main
from pyramid.catalog import load


def _env(monkeypatch):
    monkeypatch.setenv("GC_REGION", "eu_west_1")
    monkeypatch.setenv("GC_CLIENT_ID", fg.CLIENT_ID)
    monkeypatch.setenv("GC_CLIENT_SECRET", fg.CLIENT_SECRET)


def test_export_two_reports(fake, cfgdir, tmp_path, monkeypatch):
    _env(monkeypatch)
    out = tmp_path / "exports"
    assert main(["export", "users", "queues", "-o", str(out) + "/"]) == 0
    with open(out / "env_users.csv", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert rows[0][:3] == ["Name", "Username", "Email"]
    assert len(rows) == 1 + len(fake.handler.org.users)


def test_export_all_snapshot(fake, cfgdir, tmp_path, monkeypatch):
    _env(monkeypatch)
    out = tmp_path / "snap"
    assert main(["export", "all", "--format", "both", "-o", str(out)]) == 0
    assert len(list(out.glob("*.csv"))) == len(load()) == len(list(out.glob("*.json")))
    org = json.loads((out / "env_settings.json").read_text(encoding="utf-8"))
    assert org["name"] == "Lumen Harbor Telecom"


def test_export_failure_exit_code(fake, cfgdir, tmp_path, monkeypatch):
    _env(monkeypatch)
    fake.handler.fail_status["/api/v2/groups"] = 403
    assert main(["export", "groups", "-o", str(tmp_path / "g.csv")]) == 1


def test_saved_client(fake, cfgdir, tmp_path, capsys):
    from pyramid.config import OAuthClient, Store

    Store().put_client(OAuthClient("Lumen", "eu_west_1", fg.CLIENT_ID, fg.CLIENT_SECRET))
    assert main(["export", "skills", "--client", "lumen", "-o", str(tmp_path / "s.csv")]) == 0
    assert (tmp_path / "s.csv").exists()
    main(["clients"])
    assert "Lumen\teu_west_1" in capsys.readouterr().out


def test_list(capsys):
    assert main(["list"]) == 0
    assert f"{len(load())} reports" in capsys.readouterr().out
