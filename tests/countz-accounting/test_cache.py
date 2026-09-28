#!/usr/bin/env python3
"""Self-test for scripts/cache.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_cache.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import json
import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from cache import _cli, _pl, entry, manifest, note, read, scan, verify, write  # noqa: E402


def main() -> int:
    import tempfile
    pl = _pl()
    bad: list[str] = []

    def refused(label, fn, want):
        try:
            fn()
        except (ValueError, KeyError) as exc:
            if want not in str(exc):
                bad.append(f"{label}: refused, but the message lacks {want!r}: {exc}")
            return
        bad.append(f"{label}: not refused")

    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        room, rd = tdp / "room", tdp / "run"
        room.mkdir()
        rd.mkdir()
        src = room / "stacked.csv"
        src.write_text("Demo Corp\nperiod,billings\n2024-10,50.00\n2024-11,60.00\nTotal,110.00\n")
        (rd / "run.json").write_text(json.dumps({"sources": [
            {"id": "dataroom", "name": "room", "path": str(room), "kind": "folder"}]}))
        df = pl.DataFrame({"period": ["2024-10", "2024-11"], "billings": [50.0, 60.0]})
        cols = {"period": {"at": "A", "parse": "as written"},
                "billings": {"at": "B", "parse": "as written"}}
        kw = dict(file="stacked.csv", source="dataroom", file_role="management_prepared",
                  header_at="A2", rows="3:4", columns=cols, control="billings")
        e = write(rd, "roll", df, **kw, stated={"value": 110.0, "where": "B5 (Total)"},
                  script=rd / "workpapers" / "extract-x0.py")
        if e["control_total"] != {"column": "billings", "value": 110.0} or e["row_count"] != 2 \
                or e["stated"]["agrees"] is not True or e["file"] != "stacked.csv" \
                or e["script"] != "workpapers/extract-x0.py" \
                or [c["parse"] for c in e["columns"]] != ["as written", "as written"]:
            bad.append(f"write: entry {e}")
        if read(rd, "roll").height != 2 or scan(rd, "roll").collect().width != 2:
            bad.append("read/scan: the cached frame does not come back")
        # absolute path under a registered source is attributed to it
        e2 = write(rd, "roll_abs", df, **{**kw, "file": str(src), "source": None})
        if e2["source"] != "dataroom" or e2["file"] != "stacked.csv":
            bad.append(f"write: an absolute path is not attributed to its source: {e2}")
        # a stated total that disagrees is recorded, not refused
        e3 = write(rd, "roll_off", df, **kw, stated={"value": 111.0, "where": "B5"})
        if e3["stated"]["agrees"] is not False or e3["stated"]["computed"] != 110.0:
            bad.append(f"stated: a disagreement must be recorded agrees: false: {e3['stated']}")
        # no control: the row count stands in
        e4 = write(rd, "roll_rows", df, **{**kw, "control": None})
        if e4["control_total"] != {"column": None, "value": 2}:
            bad.append(f"control None: {e4['control_total']}")
        refused("id not a slug", lambda: write(rd, "Roll", df, **kw), "slug")
        refused("column set", lambda: write(rd, "r", df, **{**kw, "columns": {
            "period": cols["period"]}}), "missing ['billings']")
        refused("extra column", lambda: write(rd, "r", df, **{**kw, "columns": {
            **cols, "memo": {"at": "C", "parse": "as written"}}}), "memo")
        refused("no parse", lambda: write(rd, "r", df, **{**kw, "columns": {
            **cols, "billings": {"at": "B"}}}), "parse")
        refused("file missing", lambda: write(rd, "r", df, **{**kw, "file": "nope.csv"}),
                "file missing")
        refused("control absent", lambda: write(rd, "r", df, **{**kw, "control": "amount"}),
                "amount")
        refused("control text", lambda: write(rd, "r", df, **{**kw, "control": "period"}),
                "not numeric")
        refused("file_role", lambda: write(rd, "r", df, **{**kw, "file_role": "run_artifact"}),
                "file_role")
        refused("rows empty", lambda: write(rd, "r", df, **{**kw, "rows": ""}), "rows")
        refused("unregistered source", lambda: write(rd, "r", df, **{**kw, "source": "gl"}),
                "not registered")
        refused("unknown id", lambda: entry(rd, "nope"), "roll")
        if (rd / "cache" / "r.parquet").exists():
            bad.append("a refused write left a parquet behind")
        note(rd, "stacked.csv", source="dataroom", where="A7:B9", what="a KPI table")
        note(rd, "stacked.csv", source="dataroom", where="A7:B9", what="a KPI table, again")
        ne = manifest(rd)["not_extracted"]
        if len(ne) != 1 or ne[0]["what"] != "a KPI table, again":
            bad.append(f"note: {ne}")
        if not all(v["agrees"] for v in verify(rd)):
            bad.append(f"verify: an unchanged source must agree: {verify(rd)}")
        if _quiet([str(rd), "--verify", "roll"]) != 0:
            bad.append("--verify on an unchanged source must exit 0")
        with src.open("a") as fh:
            fh.write("x,1\n")
        v = verify(rd, "roll")
        if v[0]["agrees"] or "changed" not in (v[0]["why"] or ""):
            bad.append(f"verify: a changed source must disagree: {v}")
        if _quiet([str(rd), "--verify"]) != 3:
            bad.append("--verify on a changed source must exit 3")
        src.unlink()
        v = verify(rd, "roll")
        if v[0]["agrees"] or "missing" not in (v[0]["why"] or ""):
            bad.append(f"verify: a missing source must disagree: {v}")
    for b in bad:
        print(f"FAIL {b}", file=sys.stderr)
    print("cache.py self-check: " + ("ok" if not bad else f"{len(bad)} failure(s)"))
    return 1 if bad else 0


def _quiet(argv: list[str]) -> int:
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return _cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
