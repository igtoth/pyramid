"""The web page (web/core.js, run in Node) and the desktop app (data.py)
turn the same records into the same table and the same CSV."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pyramid import data
from pyramid.catalog import load, raw_catalog
from pyramid.fetch import fetch

CORE = Path(__file__).resolve().parents[1] / "src" / "pyramid" / "web" / "core.js"
NODE = shutil.which("node")

SCRIPT = """
import { normalizeCatalog, tableColumns, rowsOf, flattenObject, toCSV } from %s;
import { readFileSync } from "node:fs";
const input = JSON.parse(readFileSync(0, "utf8"));
const cat = normalizeCatalog(input.catalog);
const out = {};
for (const [key, res] of Object.entries(input.results)) {
  const ep = cat.byKey[key];
  if (ep.kind === "object") {
    const rows = flattenObject(res.obj);
    out[key] = { headers: ["Key", "Value"], rows, csv: toCSV(["Key", "Value"], rows) };
  } else {
    const cols = tableColumns(ep.columns, res.records);
    const rows = rowsOf(res.records, cols);
    out[key] = { headers: cols.map((c) => c.header), rows, csv: toCSV(cols.map((c) => c.header), rows) };
  }
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not NODE, reason="Node.js not installed")
def test_same_rows_and_csv_in_python_and_js(client, tmp_path):
    cat = load()
    results, expected = {}, {}
    for ep in cat.endpoints:
        res = fetch(client, ep)
        if ep.is_object:
            rows = [list(r) for r in data.flatten_object(res.obj)]
            headers = ["Key", "Value"]
            results[ep.key] = {"obj": res.obj}
        else:
            cols = data.table_columns(ep.columns, res.records)
            headers, rows = data.headers(cols), data.rows(res.records, cols)
            results[ep.key] = {"records": res.records}
        csv_path = tmp_path / f"{ep.key}.csv"
        data.write_csv(str(csv_path), headers, rows)
        expected[ep.key] = {"headers": headers, "rows": rows,
                            "csv": csv_path.read_bytes().decode("utf-8")}
    # sprinkle values the rules treat specially
    results["groups"]["records"][0]["name"] = "=1+1"
    expected["groups"]["rows"][0][0] = "=1+1"
    script = tmp_path / "parity.mjs"
    script.write_text(SCRIPT % json.dumps(CORE.as_uri()), encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], input=json.dumps({"catalog": raw_catalog(), "results": results}),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    got = json.loads(proc.stdout)
    for key, exp in expected.items():
        if key == "groups":
            assert got[key]["rows"][0][0] == "=1+1" and "'=1+1" in got[key]["csv"]
            continue
        assert got[key]["headers"] == exp["headers"], key
        assert got[key]["rows"] == exp["rows"], key
        assert got[key]["csv"] == exp["csv"], key
