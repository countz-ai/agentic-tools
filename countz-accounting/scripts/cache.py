#!/usr/bin/env python3
"""The run's cache of parsed tables: `<run_dir>/cache/<id>.parquet` and the manifest that
says where each came from. Bookkeeping only — this module parses no client file.

The `extract` step (skills/check-extract/SKILL.md) samples each file with peek.py and
writes its own script, `workpapers/extract-<check>.py`, that parses every table the
downstream steps need out of it — stacked, side by side, several per sheet — once. The
script hands each parsed table here with the coordinates it read it at:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    import cache

    cache.write(RUN, "invoice_lines_fy2025", df,
                file="3 Revenue/3.5 Invoices/Invoice Lines FY2025.csv", source="dataroom",
                file_role="system_export", header_at="A5", rows="6:1204",
                columns={"customer_id": {"at": "A", "parse": "as written, kept as text"},
                         "invoice_amount": {"at": "D",
                                            "parse": "decimal comma, thousands dot"}},
                control="invoice_amount",
                stated={"value": 1234567.89, "where": "D1206 (Total)"},
                script=RUN / "workpapers/extract-x0.py",
                what="the invoice lines, header at row 5")     # the plan's words
    cache.note(RUN, "3 Revenue/Summary.xlsx", source="dataroom",
               where="Summary!G24:K41", what="a KPI table no step reads")

`write` refuses what it cannot record exactly: an id that is not a slug, a `columns` map
that is not exactly the frame's columns each with `at` and `parse`, a file that does not
exist, a control column that is absent or not numeric, a file_role outside FILE_ROLES.
`header_at` (`"B4"`, `"line 5"`, `"p2:L3"`, `"none - columns by position"`) and `rows`
(`"5:40,42:1203"`, `"p2:L7-15,p3:L4-12"`) are recorded as the caller states them. A
`stated` total the document prints is recorded beside the computed control total with
`agrees`; a disagreement is recorded, not refused — the step rules on it.

Readers: `manifest`, `entry`, `read` (polars DataFrame), `scan` (LazyFrame),
`control_value`. `verify` is the exact re-check: the source file still exists with the
cached sha256 and byte count, and the parquet holds the recorded row count.

    cache.py <run_dir> --show              one line per id
    cache.py <run_dir> --verify [id]       exit 3 on a disagreement

Run with no arguments to self-check. Stdlib, and polars (imported when a frame is read or
written) — run as `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys

SCHEMA = "countz-accounting/cache@2"
CACHE_DIR = "cache"
MANIFEST = "manifest.json"
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# EVIDENCE.md § 1: who produced a data-room file. evidence.py adds `run_artifact` for the
# run's own tables under checks/, which are never cached.
FILE_ROLES = frozenset({"system_export", "management_prepared", "bank_statement",
                        "policy_document", "correspondence", "unknown"})
NO_ROWS = "none - no data rows"


def _pl():
    try:
        import polars as pl
    except ImportError as exc:                      # pragma: no cover
        sys.exit(f"cache.py needs polars ({exc}); run it as "
                 "`uv run --project ${CLAUDE_PLUGIN_ROOT} python3`")
    return pl


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- the run's sources

def sources(run_dir) -> dict[str, dict]:
    """The run's registered sources by id (run.json `sources`); {} with no run.json."""
    p = pathlib.Path(run_dir) / "run.json"
    if not p.is_file():
        return {}
    return {s["id"]: s for s in json.loads(p.read_text(encoding="utf-8")).get("sources", [])}


def resolve_file(run_dir, file, source: str | None = None) -> tuple[pathlib.Path, str | None, str]:
    """(absolute path, source id, path relative to that source's registered path). `file`
    is relative to the source's registered path, or absolute; an absolute path under a
    registered source is attributed to it. The file must exist."""
    raw = pathlib.Path(str(file or ""))
    if not str(file or "").strip():
        raise ValueError("no `file`")
    srcs = sources(run_dir)
    if source is not None and source not in srcs:
        raise ValueError(f"source {source!r} is not registered in run.json (registered: "
                         f"{sorted(srcs) or 'none'})")
    sid = source
    if raw.is_absolute():
        p = raw
        if not sid:
            for s in srcs.values():
                root = pathlib.Path(s["path"])
                if p == root or root in p.parents:
                    sid = s["id"]
                    break
    else:
        if not sid:
            raise ValueError(f"a relative `file` needs `source`: {raw}")
        root = pathlib.Path(srcs[sid]["path"])
        p = root if root.is_file() else root / raw
    if not p.is_file():
        raise ValueError(f"file missing: {p}")
    rel = str(p)
    if sid:
        root = pathlib.Path(srcs[sid]["path"])
        try:
            rel = str(p.relative_to(root)) if root.is_dir() else p.name
        except ValueError:
            rel = str(p)
    return p, sid, rel


# ---------------------------------------------------------------- the manifest

def _manifest_path(run_dir) -> pathlib.Path:
    return pathlib.Path(run_dir) / CACHE_DIR / MANIFEST


def manifest(run_dir) -> dict:
    """The manifest: `files` (one entry per cached id) and `not_extracted`."""
    p = _manifest_path(run_dir)
    if p.is_file():
        m = json.loads(p.read_text(encoding="utf-8"))
        m.setdefault("files", [])
        m.setdefault("not_extracted", [])
        return m
    return {"schema": SCHEMA, "written_at": None, "files": [], "not_extracted": []}


def _save(run_dir, man: dict) -> None:
    man["schema"] = SCHEMA
    man["written_at"] = _now()
    man["files"] = sorted(man.get("files", []), key=lambda e: e["id"])
    _atomic(_manifest_path(run_dir),
            json.dumps(man, indent=1, ensure_ascii=False, default=str) + "\n")


def entry(run_dir, id: str) -> dict:
    """One id's manifest entry; KeyError naming the ids the cache holds."""
    files = manifest(run_dir).get("files", [])
    for e in files:
        if e["id"] == id:
            return e
    raise KeyError(f"{id!r} is not in {_manifest_path(run_dir)}; it holds "
                   f"{[e['id'] for e in files] or 'nothing'}")


def read(run_dir, id: str):
    """The cached table as a polars DataFrame, typed as written."""
    return _pl().read_parquet(pathlib.Path(run_dir) / entry(run_dir, id)["parquet"])


def scan(run_dir, id: str):
    """The cached table as a polars LazyFrame — for a large table read in part."""
    return _pl().scan_parquet(pathlib.Path(run_dir) / entry(run_dir, id)["parquet"])


def control_value(df, col: str | None) -> float | int:
    """The sum of `col` over the frame; the row count when `col` is None. A column that is
    not numeric has no control total: refused, never summed over the cells that are."""
    if col is None:
        return df.height
    if col not in df.columns:
        raise ValueError(f"control column {col!r} is not in the frame; it has {df.columns}")
    t = df.schema[col]
    if not t.is_numeric():
        raise ValueError(f"control column {col!r} is {t}, not numeric: a cell in it did not "
                         f"read as a number, so no total is taken over it")
    v = df[col].sum()
    return round(float(v), 4) if v is not None else 0.0


# ---------------------------------------------------------------- writing

def _columns(df, columns) -> list[dict]:
    if not isinstance(columns, dict):
        raise ValueError("`columns` maps each of the frame's columns to "
                         "{\"at\": <letter or chars 41-50>, \"parse\": <how it was read>}")
    missing = [c for c in df.columns if c not in columns]
    extra = [c for c in columns if c not in df.columns]
    if missing or extra:
        raise ValueError(f"`columns` must be exactly the frame's columns: missing "
                         f"{missing}, not in the frame {extra}")
    out = []
    for c in df.columns:
        spec = columns[c]
        bad = [k for k in ("at", "parse")
               if not isinstance(spec, dict) or not isinstance(spec.get(k), str)
               or not spec[k].strip()]
        if bad:
            raise ValueError(f"column {c!r}: no {' / '.join(bad)} - `at` is where it sits "
                             f"(a letter, or chars 41-50), `parse` how its text was read "
                             f"('as written', 'decimal comma, thousands dot', ...)")
        out.append({"name": c, "at": spec["at"].strip(), "dtype": str(df.schema[c]),
                    "parse": spec["parse"].strip()})
    return out


def _stated(stated, computed) -> dict | None:
    if stated is None:
        return None
    ok = isinstance(stated, dict) and isinstance(stated.get("where"), str) \
        and stated["where"].strip() and isinstance(stated.get("value"), (int, float)) \
        and not isinstance(stated.get("value"), bool)
    if not ok:
        raise ValueError("`stated` is {\"value\": <the total the document states>, "
                         "\"where\": \"<the page/line or cell that states it>\"}")
    value = float(stated["value"])
    return {"value": value, "where": stated["where"].strip(), "computed": computed,
            "agrees": abs(round(float(computed) - value, 4)) <= 0.005}


def write(run_dir, id: str, frame, *, file, source: str | None, file_role: str,
          header_at: str, rows: str, columns: dict, control: str | None,
          sheet: str | None = None, stated: dict | None = None, script=None,
          what: str | None = None) -> dict:
    """Cache one parsed table as `cache/<id>.parquet` with its manifest entry, both
    written atomically; returns the entry. An id written again is replaced."""
    pl = _pl()
    run_dir = pathlib.Path(run_dir).resolve()
    if not isinstance(id, str) or not SLUG.match(id):
        raise ValueError(f"id {id!r} is not a slug ([a-z0-9][a-z0-9_-]*)")
    if file_role not in FILE_ROLES:
        raise ValueError(f"file_role {file_role!r}; one of {', '.join(sorted(FILE_ROLES))}")
    if hasattr(frame, "collect"):
        frame = frame.collect()
    if not isinstance(frame, pl.DataFrame):
        raise ValueError(f"frame is a {type(frame).__name__}, not a polars DataFrame")
    if frame.width == 0:
        raise ValueError(f"{id}: the frame has no columns")
    path, sid, rel = resolve_file(run_dir, file, source)
    cols = _columns(frame, columns)
    if not isinstance(header_at, str) or not header_at.strip():
        raise ValueError("`header_at` is where the header sits: a cell (\"B4\"), \"line 5\", "
                         "\"p2:L3\" or \"none - columns by position\"")
    if frame.height and (not isinstance(rows, str) or not rows.strip()):
        raise ValueError("`rows` is the data rows as they sit in the file: \"5:40,42:1203\" "
                         "or \"p2:L7-15,p3:L4-12\"")
    if control is not None and control not in frame.columns:
        raise ValueError(f"control column {control!r} is not in the frame; it has "
                         f"{frame.columns}")
    total = control_value(frame, control)
    out = run_dir / CACHE_DIR / f"{id}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    frame.write_parquet(tmp)
    tmp.replace(out)
    if script is not None:
        sp = pathlib.Path(script)
        try:
            script = str(sp.resolve().relative_to(run_dir))
        except ValueError:
            script = str(sp)
    if what is not None and (not isinstance(what, str) or not what.strip()):
        raise ValueError(f"{id}: `what` is the plan's words for the table, got {what!r}")
    e = {"id": id, "what": what, "file": rel, "source": sid, "file_role": file_role,
         "sha256": sha256(path), "bytes": path.stat().st_size, "sheet": sheet,
         "header_at": header_at.strip(),
         "rows": rows.strip() if isinstance(rows, str) and rows.strip() else NO_ROWS,
         "columns": cols, "row_count": frame.height,
         "control_total": {"column": control, "value": total}}
    st = _stated(stated, total)
    if st is not None:
        e["stated"] = st
    e.update({"parquet": f"{CACHE_DIR}/{id}.parquet", "script": script,
              "written_at": _now()})
    man = manifest(run_dir)
    man["files"] = [x for x in man["files"] if x["id"] != id] + [e]
    _save(run_dir, man)
    return e


def note(run_dir, file, *, where: str, what: str, source: str | None = None) -> dict:
    """Record a table on a file that no downstream step needs, so it is seen and not
    extracted: `where` (`"Summary!G24:K41"`, `"p4:L1-30"`), `what` in words. The same
    file and `where` noted again is replaced."""
    for k, v in (("file", file), ("where", where), ("what", what)):
        if not isinstance(v, (str, pathlib.PurePath)) or not str(v).strip():
            raise ValueError(f"`{k}` is required")
    n = {"file": str(file), "source": source, "where": where.strip(), "what": what.strip()}
    man = manifest(run_dir)
    man["not_extracted"] = [x for x in man["not_extracted"]
                            if (x.get("file"), x.get("source"), x.get("where"))
                            != (n["file"], source, n["where"])] + [n]
    _save(run_dir, man)
    return n


# ---------------------------------------------------------------- the exact re-check

def verify(run_dir, id: str | None = None) -> list[dict]:
    """Per id, `{id, agrees, why}`: the source file exists with the cached sha256 and
    bytes, and the parquet holds the recorded row count. Exact only — nothing is
    re-parsed. `why` is None when it agrees."""
    pl = _pl()
    run_dir = pathlib.Path(run_dir).resolve()
    ents = [entry(run_dir, id)] if id is not None else manifest(run_dir)["files"]
    out = []
    for e in ents:
        why = None
        try:
            path, _, _ = resolve_file(run_dir, e["file"], e.get("source"))
        except ValueError as exc:
            why = f"source {exc}"
        else:
            size = path.stat().st_size
            if size != e.get("bytes"):
                why = f"the source file changed: {size} bytes, cached {e.get('bytes')}"
            elif sha256(path) != e.get("sha256"):
                why = "the source file changed: its sha256 differs from the cached one"
        if why is None:
            pq = run_dir / e["parquet"]
            if not pq.is_file():
                why = f"parquet missing: {pq}"
            else:
                n = pl.scan_parquet(pq).select(pl.len()).collect().item()
                if n != e["row_count"]:
                    why = f"the parquet holds {n} rows, the manifest {e['row_count']}"
        out.append({"id": e["id"], "agrees": why is None, "why": why})
    return out


# ---------------------------------------------------------------- command line

def show_line(e: dict) -> str:
    ct = e.get("control_total") or {}
    ctl = f"{ct.get('column')} {ct.get('value')}" if ct.get("column") else "rows"
    sheet = f" [{e['sheet']}]" if e.get("sheet") else ""
    stated = ""
    if e.get("stated"):
        s = e["stated"]
        stated = f"  stated {s['value']} at {s['where']}: {'agrees' if s['agrees'] else 'DISAGREES'}"
    what = f"  ({e['what']})" if e.get("what") else ""
    return (f"{e['id']}{what}  {e['file']}{sheet}  rows {e['rows']}  {e['row_count']} row(s)  "
            f"control {ctl}{stated}")


def self_check() -> int:
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


def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="cache.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=pathlib.Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true", help="one line per cached id")
    g.add_argument("--verify", nargs="?", const="", metavar="ID",
                   help="re-check sources and parquets exactly; exit 3 on a disagreement")
    a = ap.parse_args(argv)
    try:
        if a.show:
            man = manifest(a.run_dir)
            for e in man["files"]:
                print(show_line(e))
            for n in man["not_extracted"]:
                print(f"not extracted: {n['file']} {n['where']} - {n['what']}")
            return 0
        res = verify(a.run_dir, a.verify or None)
    except (ValueError, KeyError) as exc:
        print(f"cache.py: {exc}", file=sys.stderr)
        return 1
    for r in res:
        print(f"{'AGREES' if r['agrees'] else 'DISAGREES'}: {r['id']}"
              + (f" - {r['why']}" if r["why"] else ""))
    return 0 if all(r["agrees"] for r in res) else 3


def main() -> int:
    if len(sys.argv) == 1:
        return self_check()
    return _cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
