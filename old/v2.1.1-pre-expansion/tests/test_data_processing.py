"""
Unit tests for GCApplication.process_data()

Run from project root:
    pytest tests/ -v

These tests use minimal stubs so they can run in CI without
a Windows desktop, Tkinter display, or Genesys Cloud SDK.
"""

import json
import sys
import types
import importlib
import pathlib
import pytest

# ── Minimal stubs ─────────────────────────────────────────────────────────────

def _stub_module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

# winreg
_stub_module("winreg", KEY_READ=0, KEY_WRITE=0,
             HKEY_CURRENT_USER=0, REG_SZ=0,
             OpenKey=lambda *a,**k: None,
             CreateKey=lambda *a,**k: None,
             CloseKey=lambda *a,**k: None,
             QueryValueEx=lambda *a,**k: ("",0),
             SetValueEx=lambda *a,**k: None,
             EnumValue=lambda *a,**k: (_ for _ in ()).throw(WindowsError(259,"")),
             DeleteValue=lambda *a,**k: None)

# tkinter family
for _mod in ["tkinter","tkinter.ttk","tkinter.filedialog",
             "tkinter.messagebox","tkinter.font","tkinter.scrolledtext"]:
    _stub_module(_mod, Tk=object, Frame=object, StringVar=object,
                 END="end", BOTH="both", WORD="word", NORMAL="normal",
                 DISABLED="disabled", BooleanVar=object)

# PIL
_pil = _stub_module("PIL")
for _sub in ["Image","ImageTk","ImageDraw"]:
    _stub_module(f"PIL.{_sub}")

# PureCloudPlatformClientV2
_pc = _stub_module("PureCloudPlatformClientV2")
_pc.configuration = types.SimpleNamespace(proxy=None)
_stub_module("PureCloudPlatformClientV2.rest")

# configparser already in stdlib — no stub needed

# ── Load module ───────────────────────────────────────────────────────────────

_src = pathlib.Path(__file__).parent.parent / "src" / "pyramid.py"

class _FakeApp:
    """Thin wrapper exposing only process_data for testing."""
    _data_cache = {}
    active_client_id = "test-client"
    selected_client_name = "Test Org"

# Exec only the process_data method by patching __init__
_spec = importlib.util.spec_from_file_location("pyramid", _src)
_mod  = importlib.util.module_from_spec(_spec)

# Prevent GUI from launching during import
import unittest.mock as mock
with mock.patch("tkinter.Tk"), \
     mock.patch("tkinter.Frame"), \
     mock.patch.dict(sys.modules, {"tkinter": sys.modules["tkinter"]}):
    try:
        _spec.loader.exec_module(_mod)
        _FakeApp.process_data = _mod.GCApplication.process_data
    except Exception:
        pass  # GUI init failure is expected; process_data is still attached

# ── Tests ─────────────────────────────────────────────────────────────────────

app = _FakeApp()


def _wrap(entities):
    """Wrap a list of dicts in the SDK page format."""
    return [{"entities": entities}]


def test_process_data_basic_user():
    raw = _wrap([{"id": "u1", "name": "Alice", "username": "alice@example.com",
                  "division": {"name": "Sales"}, "state": "active"}])
    result = app.process_data(raw, None)
    assert isinstance(result, list)
    assert result[0]["name"] == "Alice"
    assert result[0]["division"] == "Sales"   # simplified from dict


def test_process_data_removes_keys():
    raw = _wrap([{"id": "u1", "name": "Bob", "secret_field": "hidden"}])
    result = app.process_data(raw, ["secret_field"])
    assert "secret_field" not in result[0]
    assert result[0]["name"] == "Bob"


def test_process_data_queues_joined():
    raw = _wrap([{"id": "u1", "name": "Carol",
                  "queues": [{"name": "Support"}, {"name": "Billing"}]}])
    result = app.process_data(raw, None)
    assert "Support" in result[0]["queues"]
    assert "Billing" in result[0]["queues"]


def test_process_data_none_becomes_na():
    raw = _wrap([{"id": "u1", "name": None}])
    result = app.process_data(raw, None)
    assert result[0]["name"] == "N/A"


def test_process_data_empty_list():
    result = app.process_data([], None)
    assert result == []


def test_process_data_non_list_passthrough():
    """Non-list input is returned as-is (e.g. org settings object)."""
    obj = {"org_id": "123", "name": "Test Org"}
    result = app.process_data(obj, None)
    assert result == obj
