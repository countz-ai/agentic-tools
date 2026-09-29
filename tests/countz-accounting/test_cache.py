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
    _refusals_first(pl, bad, refused)
    _control(pl, bad, refused)
    _stated_and_verify(pl, bad, refused)
    _resolve(pl, bad, refused)
    _concurrent(pl, bad)
    for b in bad:
        print(f"FAIL {b}", file=sys.stderr)
    print("cache.py self-check: " + ("ok" if not bad else f"{len(bad)} failure(s)"))
    return 1 if bad else 0


def _quiet(argv: list[str]) -> int:
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return _cli(argv)


def _room(td) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """(tmp root resolved, the data room, the run dir) with `a.csv` registered."""
    tdp = pathlib.Path(td).resolve()
    room, rd = tdp / "room", tdp / "run"
    room.mkdir()
    rd.mkdir()
    (room / "a.csv").write_text("x,amt\n1,10\n2,20\n")
    (rd / "run.json").write_text(json.dumps({"sources": [
        {"id": "dataroom", "name": "room", "path": str(room), "kind": "folder"}]}))
    return tdp, room, rd


def _kw(df, **over) -> dict:
    kw = dict(file="a.csv", source="dataroom", file_role="system_export", header_at="A1",
              rows="2:3", columns={c: {"at": "A", "parse": "as written"} for c in df.columns},
              control="amt")
    kw.update(over)
    return kw


def _refusals_first(pl, bad, refused) -> None:
    """A refused write leaves the parquet and the manifest as they were; a slug is the
    whole id; an Object column is refused with no temporary file left behind."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        _, _, rd = _room(td)
        a = pl.DataFrame({"x": [1, 2], "amt": [10.0, 20.0]})
        b = pl.DataFrame({"x": [1, 2], "amt": [999.0, 1000.0]})
        write(rd, "t", a, **_kw(a))
        for label, extra in (("malformed stated", {"stated": {"value": "30", "where": "B4"}}),
                             ("blank what", {"what": "   "}),
                             ("blank sheet", {"sheet": ""})):
            refused(label, lambda: write(rd, "t", b, **_kw(b), **extra), "")
            if read(rd, "t")["amt"].sum() != 30.0 or entry(rd, "t")["control_total"]["value"] != 30.0:
                bad.append(f"{label}: a refused write replaced the parquet or the entry")
        if not verify(rd, "t")[0]["agrees"]:
            bad.append(f"refused writes: the cache no longer verifies: {verify(rd, 't')}")
        e = write(rd, "t", b, **_kw(b), what="the rewrite")      # the valid neighbour
        if read(rd, "t")["amt"].sum() != 1999.0 or e["control_total"]["value"] != 1999.0:
            bad.append(f"a valid rewrite of an id did not replace it: {e['control_total']}")
        refused("id with a trailing newline", lambda: write(rd, "t2\n", a, **_kw(a)), "slug")
        if (rd / "cache" / "t2\n.parquet").exists():
            bad.append("a newline id left a parquet behind")
        o = pl.DataFrame({"x": [1, 2], "o": pl.Series([object(), object()], dtype=pl.Object)})
        refused("Object column", lambda: write(rd, "t8", o, **_kw(o, control=None)),
                "Object-typed")
        left = [p.name for p in (rd / "cache").iterdir() if p.name.endswith(".tmp")]
        if left:
            bad.append(f"temporary files left in the cache: {left}")
        refused("note where as a path", lambda: note(rd, "a.csv", where=pathlib.Path("A1"),
                                                     what="x"), "where")


def _control(pl, bad, refused) -> None:
    """The control total is exact in a wide type, and a null or NaN cell is refused."""
    import decimal
    from cache import control_value
    f32 = pl.DataFrame({"amt": pl.Series([12345.67] * 100_000, dtype=pl.Float32)})
    want = round(__import__("math").fsum(f32["amt"].cast(pl.Float64).to_list()), 4)
    if control_value(f32, "amt") != want:
        bad.append(f"Float32 control not widened: {control_value(f32, 'amt')} != {want}")
    big = pl.DataFrame({"amt": [2**62, 2**62]})
    if control_value(big, "amt") != 2**63:
        bad.append(f"Int64 control overflowed: {control_value(big, 'amt')}")
    odd = pl.DataFrame({"amt": [2**53 + 1]})
    if control_value(odd, "amt") != 2**53 + 1 or not isinstance(control_value(odd, "amt"), int):
        bad.append(f"integer control not exact: {control_value(odd, 'amt')!r}")
    dec = pl.DataFrame({"amt": pl.Series([decimal.Decimal("0.10"), decimal.Decimal("0.20")],
                                         dtype=pl.Decimal(10, 2))})
    if control_value(dec, "amt") != 0.3:
        bad.append(f"Decimal control not exact: {control_value(dec, 'amt')!r}")
    huge = pl.DataFrame({"amt": pl.Series([decimal.Decimal("12345678901234567.89")],
                                          dtype=pl.Decimal(38, 2))})
    refused("Decimal total beyond a float", lambda: control_value(huge, "amt"), "float")
    cast = pl.DataFrame({"amt": ["10", "20", "1.234,50"]}).with_columns(
        pl.col("amt").cast(pl.Float64, strict=False))
    refused("null from a failed cast", lambda: control_value(cast, "amt"), "null")
    refused("every cell null", lambda: control_value(cast.filter(pl.col("amt").is_null()), "amt"),
            "null")
    refused("NaN cell", lambda: control_value(pl.DataFrame({"amt": [1.0, float("nan")]}), "amt"),
            "NaN")
    refused("Null-typed column", lambda: control_value(pl.DataFrame({"amt": []}), "amt"), "Null")
    filled = cast.with_columns(pl.col("amt").fill_null(0))       # the valid neighbour
    if control_value(filled, "amt") != 30.0:
        bad.append(f"a filled column's control: {control_value(filled, 'amt')}")
    if control_value(pl.DataFrame({"amt": pl.Series([], dtype=pl.Float64)}), "amt") != 0.0:
        bad.append("an empty typed column's control is not 0")


def _stated_and_verify(pl, bad, refused) -> None:
    """`stated` takes any finite number and an optional tolerance; verify re-checks the
    parquet's content and reports an unreadable one as a disagreement."""
    import decimal
    import tempfile
    import numpy as np
    with tempfile.TemporaryDirectory() as td:
        _, _, rd = _room(td)
        a = pl.DataFrame({"x": [1, 2], "amt": [10.0, 20.0]})
        for v in (decimal.Decimal("30.00"), np.int64(30), np.float64(30.0), 30):
            try:
                st = write(rd, "s", a, **_kw(a), stated={"value": v, "where": "B4"})["stated"]
                if st["agrees"] is not True or st["tolerance"] != 0.005:
                    bad.append(f"stated {type(v).__name__}: {st}")
            except ValueError as exc:
                bad.append(f"stated {type(v).__name__} refused: {exc}")
        one = pl.DataFrame({"x": [1], "amt": [1.000]})
        st = write(rd, "k", one, **_kw(one, rows="2:2"),
                   stated={"value": 1.004, "where": "B4", "tolerance": 0.0005})["stated"]
        if st["agrees"] is not False or st["tolerance"] != 0.0005:
            bad.append(f"stated tolerance not applied: {st}")
        for label, s, want in (("unknown stated key", {"value": 1, "where": "B4", "note": "x"},
                                "note"),
                               ("negative tolerance", {"value": 1, "where": "B4",
                                                       "tolerance": -1}, "negative"),
                               ("NaN stated", {"value": float("nan"), "where": "B4"}, "finite"),
                               ("bool stated", {"value": True, "where": "B4"}, "number")):
            refused(label, lambda s=s: write(rd, "k2", one, **_kw(one, rows="2:2"), stated=s),
                    want)
        write(rd, "d", a, **_kw(a))
        pl.DataFrame({"x": [7, 8], "amt": [1.0, 2.0]}).write_parquet(rd / "cache" / "d.parquet")
        v = verify(rd, "d")[0]
        if v["agrees"] or "parquet changed" not in (v["why"] or ""):
            bad.append(f"verify: a parquet rewritten with the same row count must disagree: {v}")
        (rd / "cache" / "d.parquet").write_bytes(b"garbage")
        v = verify(rd, "d")[0]
        if v["agrees"]:
            bad.append(f"verify: a corrupt parquet must disagree: {v}")
        if _quiet([str(rd), "--verify", "d"]) != 3:
            bad.append("--verify on a corrupt parquet must exit 3")
        if not verify(rd, "s")[0]["agrees"]:
            bad.append(f"verify: an untouched id must still agree: {verify(rd, 's')}")
        man = json.loads((rd / "cache" / "manifest.json").read_text())
        man["schema"] = "countz-accounting/cache@1"
        (rd / "cache" / "manifest.json").write_text(json.dumps(man))
        refused("a foreign manifest schema", lambda: manifest(rd), "schema")
        refused("a write over a foreign manifest", lambda: write(rd, "s", a, **_kw(a)), "schema")


def _resolve(pl, bad, refused) -> None:
    """A file is attributed to the deepest source that holds it, through symlinked
    directories; a file outside the named source, a climb out of it, or a wrong name for
    a one-file source is refused."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp, room, rd = _room(td)
        (room / "bank").mkdir()
        (room / "bank" / "stmt.csv").write_text("x,amt\n1,10\n2,20\n")
        other = tdp / "elsewhere"
        other.mkdir()
        (other / "b.csv").write_text("x,amt\n1,10\n2,20\n")
        (tdp / "gl.csv").write_text("x,amt\n1,10\n2,20\n")
        (tdp / "roomlink").symlink_to(room)
        (rd / "run.json").write_text(json.dumps({"sources": [
            {"id": "dataroom", "path": str(room)}, {"id": "bank", "path": str(room / "bank")},
            {"id": "gl", "path": str(tdp / "gl.csv")}]}))
        a = pl.DataFrame({"x": [1, 2], "amt": [10.0, 20.0]})
        e = write(rd, "r1", a, **_kw(a, file=str(tdp / "roomlink" / "a.csv"), source=None))
        if (e["source"], e["file"]) != ("dataroom", "a.csv"):
            bad.append(f"a path through a symlinked directory is not attributed: {e['source']} "
                       f"{e['file']}")
        e = write(rd, "r2", a, **_kw(a, file=str(room / "bank" / "stmt.csv"), source=None))
        if (e["source"], e["file"]) != ("bank", "stmt.csv"):
            bad.append(f"nested sources: not the deepest: {e['source']} {e['file']}")
        e = write(rd, "r3", a, **_kw(a, file=str(other / "b.csv"), source=None))
        if (e["source"], e["file"]) != (None, str(other / "b.csv")):
            bad.append(f"a file under no source: {e['source']} {e['file']}")
        refused("file outside the named source", lambda: write(
            rd, "r", a, **_kw(a, file=str(other / "b.csv"), source="dataroom")), "not under")
        refused("a climb out of the source", lambda: write(
            rd, "r", a, **_kw(a, file="../elsewhere/b.csv")), "climbs out")
        refused("a one-file source named wrongly", lambda: write(
            rd, "r", a, **_kw(a, file="other.xlsx", source="gl")), "one file")
        e = write(rd, "r4", a, **_kw(a, file="gl.csv", source="gl"))
        if (e["source"], e["file"]) != ("gl", "gl.csv") or not verify(rd, "r4")[0]["agrees"]:
            bad.append(f"a one-file source named rightly: {e['source']} {e['file']}")
        e = write(rd, "r5", a, **_kw(a, file="bank/stmt.csv"))
        if (e["source"], e["file"]) != ("dataroom", "bank/stmt.csv"):
            bad.append(f"a relative file inside its source: {e['source']} {e['file']}")
        if not all(v["agrees"] for v in verify(rd)):
            bad.append(f"verify after attribution: {verify(rd)}")


def _write_many(args) -> None:
    rd, i = args
    import polars as pl
    df = pl.DataFrame({"x": [1, 2], "amt": [10.0, 20.0 + i]})
    for j in range(5):
        write(rd, f"w{i}-{j}", df, **_kw(df))
        write(rd, "shared", df, **_kw(df))


def _concurrent(pl, bad) -> None:
    """Writers in separate processes never lose a manifest entry, and every parquet
    matches its entry."""
    import concurrent.futures
    import multiprocessing
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        _, _, rd = _room(td)
        with concurrent.futures.ProcessPoolExecutor(
                4, mp_context=multiprocessing.get_context("spawn")) as ex:
            list(ex.map(_write_many, [(str(rd), i) for i in range(4)]))
        held = {e["id"] for e in manifest(rd)["files"]}
        parquets = {p.stem for p in (rd / "cache").glob("*.parquet")}
        if parquets != held or len(held) != 21:
            bad.append(f"concurrent writers: {len(parquets)} parquets, {len(held)} entries, "
                       f"lost {sorted(parquets - held)}")
        if not all(v["agrees"] for v in verify(rd)):
            bad.append(f"concurrent writers: a parquet does not match its entry: {verify(rd)}")


if __name__ == "__main__":
    raise SystemExit(main())
