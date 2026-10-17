from pyramid import data
from pyramid.catalog import Column


def test_resolve_nested_and_lists():
    rec = {"division": {"name": "EMEA"}, "queues": [{"name": "A"}, {"name": "B"}, {}], "tags": ["x", "y"]}
    assert data.resolve(rec, "division.name") == "EMEA"
    assert data.resolve(rec, "queues.name") == ["A", "B"]
    assert data.resolve(rec, "missing.name") is None
    assert data.resolve(rec, "tags") == ["x", "y"]
    assert data.resolve({"a": "text"}, "a.b") is None


def test_cell_formats():
    assert data.cell(None) == ""
    assert data.cell(True) == "true"
    assert data.cell(3) == "3"
    assert data.cell({"name": "Billing", "id": "1"}) == "Billing"
    assert data.cell({"id": "abc"}) == "abc"
    assert data.cell({}) == ""
    assert data.cell(["a", "", None, "b"]) == "a; b"
    assert data.cell({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_rows_and_id_column():
    recs = [{"id": "1", "name": "Ana", "division": {"name": "Home"}}, {"id": "2", "name": "Bo"}]
    cols = data.table_columns([Column("Name", "name"), Column("Division", "division.name")], recs)
    assert [c.header for c in cols] == ["Name", "Division", "ID"]
    assert data.rows(recs, cols) == [["Ana", "Home", "1"], ["Bo", "", "2"]]


def test_no_phantom_columns():
    """v2 added division/schema/... as N/A to every record; v3 shows only what exists."""
    cols = data.table_columns([Column("Name", "name")], [{"name": "x"}])
    assert [c.header for c in cols] == ["Name"]


def test_flatten_object():
    obj = {"name": "Org", "features": {"pci": True, "hipaa": False}, "selfUri": "/x",
           "list": [{"a": 1}, {"a": 2}], "empty": {}}
    assert data.flatten_object(obj) == [("empty", ""), ("features.hipaa", "false"), ("features.pci", "true"),
                                        ("list[0].a", "1"), ("list[1].a", "2"), ("name", "Org")]


def test_csv_injection_guard_and_bom(tmp_path):
    p = tmp_path / "x.csv"
    n = data.write_csv(str(p), ["Name", "Note"], [["=HYPERLINK(\"http://x\")", "+1"], ["-2", "@cmd"], ["ok", "Ação"]])
    assert n == 3
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").splitlines()
    assert text[1] == "\"'=HYPERLINK(\"\"http://x\"\")\",'+1"
    assert text[2] == "'-2,'@cmd"
    assert text[3] == "ok,Ação"


def test_strip_fields():
    recs = [{"id": 1, "secret": "s"}, {"id": 2}]
    data.strip_fields(recs, ["secret"])
    assert recs == [{"id": 1}, {"id": 2}]
