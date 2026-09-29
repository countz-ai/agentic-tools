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

`write` refuses what it cannot record exactly, before it touches the parquet or the
manifest: an id that is not a slug (`[a-z0-9][a-z0-9_-]*`, the whole
string), a `columns` map that is not exactly the frame's columns each with `at` and
`parse`, an Object-typed column (parquet holds typed columns only), a file that does not
resolve (`resolve_file`), a file_role outside FILE_ROLES, a control column that
`control_value` refuses, a `stated` or `what` of the wrong form. `header_at` (`"B4"`,
`"line 5"`, `"p2:L3"`, `"none - columns by position"`) and `rows` (`"5:40,42:1203"`,
`"p2:L7-15,p3:L4-12"`) are recorded as the caller states them; `sheet`, when given, is a
non-empty string. A `stated` total the document prints is recorded beside the computed
control total with `agrees` (the two differ by no more than its `tolerance`, 0.005 unless
the call states one). A disagreement is recorded for the step to rule on. The source's
sha256 and bytes are read when `write` is called: parse and write a table with the file
unchanged in between.

**The control total** is exact or refused (`control_value`). A null, NaN or infinite cell
in the control column is refused. A blank that means zero is filled by the script
(`fill_null(0)`) and said in the column's `parse`.

**Concurrent writers.** `write` and `note` hold an exclusive lock
(`cache/.manifest.lock`, fcntl, POSIX) while they replace the parquet and rewrite the
manifest, so concurrent extract scripts never lose an entry. Every read checks the
manifest's `schema` and refuses another version's.

Readers: `manifest`, `entry`, `read` (polars DataFrame), `scan` (LazyFrame),
`control_value`. `verify` is the exact re-check: the source file still exists with the
cached sha256 and byte count, the parquet still has the sha256 recorded when it was
written, and it holds the recorded row count. A file or parquet that cannot be read is
reported as a disagreement.

    cache.py <run_dir> --show              one line per id
    cache.py <run_dir> --verify [id]       exit 3 on a disagreement

Stdlib, and polars (imported when a frame is read or
written) — run as `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import decimal
import hashlib
import json
import math
import os
import pathlib
import re
import sys
import tempfile

SCHEMA = "countz-accounting/cache@3"
CACHE_DIR = "cache"
MANIFEST = "manifest.json"
LOCK = ".manifest.lock"
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]*")          # matched with fullmatch
STATED_TOLERANCE = 0.005
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
    return _digest(path)[0]


def _digest(path: pathlib.Path) -> tuple[str, int]:
    """(sha256, bytes) of one read of the file."""
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def _tmp_beside(path: pathlib.Path) -> pathlib.Path:
    """A temporary file next to `path`, unique per call (same filesystem, so `replace` is
    atomic)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    return pathlib.Path(name)


def _atomic(path: pathlib.Path, text: str) -> None:
    tmp = _tmp_beside(path)
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


@contextlib.contextmanager
def _locked(run_dir):
    """Hold the cache's exclusive lock: one writer at a time reads, changes and saves the
    manifest (and replaces a parquet with it)."""
    import fcntl                                   # POSIX only: macOS and Linux
    p = pathlib.Path(run_dir) / CACHE_DIR / LOCK
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ---------------------------------------------------------------- the run's sources

def sources(run_dir) -> dict[str, dict]:
    """The run's registered sources by id (run.json `sources`); {} with no run.json."""
    p = pathlib.Path(run_dir) / "run.json"
    if not p.is_file():
        return {}
    return {s["id"]: s for s in json.loads(p.read_text(encoding="utf-8")).get("sources", [])}


def _under(p: pathlib.Path, root: pathlib.Path) -> tuple[str, int] | None:
    """(`p` relative to `root` as posix, the depth of the root matched) when `p` lies
    under `root` (or is it: `""`), reading both as written and with their directories'
    symlinks resolved (`/tmp` and `/private/tmp` are one place); None otherwise. A file
    that is itself a symlink keeps its own name."""
    a = pathlib.Path(os.path.abspath(p))
    cands = (a, a.parent.resolve() / a.name)
    ra = pathlib.Path(os.path.abspath(root))
    for r in (ra, ra.resolve()):
        for c in cands:
            if c == r:
                return "", len(r.parts)
            if r in c.parents:
                return c.relative_to(r).as_posix(), len(r.parts)
    return None


def resolve_file(run_dir, file, source: str | None = None) -> tuple[pathlib.Path, str | None, str]:
    """(absolute path, source id, path relative to that source's registered path). `file`
    is relative to the source's registered path, or absolute. An absolute path under a
    registered source — through a symlinked directory or an alias such as `/tmp` for
    `/private/tmp` included — is attributed to the most specific (deepest) source that
    holds it; one under no source keeps its absolute path and no source. For a source
    registered as one file, `file` is that file's name or its path, and the relative path
    is its name. Refused: no `file`; a `source` not registered in run.json; a relative
    `file` with no `source`, or one that climbs out of its source (`..`); a `file` that
    is not under the `source` named; for a one-file source, a `file` naming another file;
    a file that does not exist."""
    if file is None or not isinstance(file, (str, os.PathLike)) or not str(file).strip():
        raise ValueError("no `file`")
    raw = pathlib.Path(str(file))
    srcs = sources(run_dir)
    if source is not None and source not in srcs:
        raise ValueError(f"source {source!r} is not registered in run.json (registered: "
                         f"{sorted(srcs) or 'none'})")
    sid = source
    if raw.is_absolute():
        p = raw
        if sid is not None:
            hit = _under(p, pathlib.Path(srcs[sid]["path"]))
            if hit is None:
                raise ValueError(f"file {p} is not under source {sid!r} "
                                 f"({srcs[sid]['path']}); name the source that holds it, "
                                 f"or none")
            rel = hit[0]
        else:
            hits = [(h[1], s["id"], h[0]) for s in srcs.values()
                    if (h := _under(p, pathlib.Path(s["path"]))) is not None]
            if hits:
                _, sid, rel = max(hits)
            else:
                rel = str(p)
    else:
        if sid is None:
            raise ValueError(f"a relative `file` needs `source`: {raw}")
        root = pathlib.Path(srcs[sid]["path"])
        if root.is_file():
            if len(raw.parts) != 1 or raw.name != root.name:
                raise ValueError(f"source {sid!r} is the one file {root.name!r}; `file` "
                                 f"{str(raw)!r} names another")
            p, rel = root, ""
        else:
            p = root / raw
            hit = _under(p, root)
            if hit is None or not hit[0]:
                raise ValueError(f"file {str(raw)!r} climbs out of source {sid!r} "
                                 f"({root}); name it from inside the source")
            rel = hit[0]
    if not p.is_file():
        raise ValueError(f"file missing: {p}")
    if sid is not None and not rel:
        rel = p.name                              # the source is this one file
    return p, sid, rel


# ---------------------------------------------------------------- the manifest

def _manifest_path(run_dir) -> pathlib.Path:
    return pathlib.Path(run_dir) / CACHE_DIR / MANIFEST


def manifest(run_dir) -> dict:
    """The manifest: `files` (one entry per cached id) and `not_extracted`. Refused: a
    manifest that is not JSON, or whose `schema` is not SCHEMA."""
    p = _manifest_path(run_dir)
    if not p.is_file():
        return {"schema": SCHEMA, "written_at": None, "files": [], "not_extracted": []}
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{p}: not a cache manifest ({exc})") from None
    got = m.get("schema") if isinstance(m, dict) else None
    if got != SCHEMA:
        raise ValueError(f"{p}: schema {got!r}, not {SCHEMA!r} - written by another "
                         f"version of cache.py; delete {p.parent} and re-run the extract "
                         f"step's script")
    m.setdefault("files", [])
    m.setdefault("not_extracted", [])
    return m


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
    """The sum of `col` over the frame; the row count when `col` is None. Summed exactly:
    an integer column as a whole number (an int), a float column — Float32 widened — as
    the correctly rounded sum of its cells (`math.fsum`), a Decimal column exactly; a
    float or Decimal total is returned as a float rounded to 4 places. Refused: a column
    that is not numeric, a null cell (one a `strict=False` cast could not read, or a
    blank the script did not fill), a NaN or infinite cell, and a Decimal total a float
    cannot hold to 4 places."""
    pl = _pl()
    if col is None:
        return df.height
    if col not in df.columns:
        raise ValueError(f"control column {col!r} is not in the frame; it has {df.columns}")
    t = df.schema[col]
    if t == pl.Null:
        raise ValueError(f"control column {col!r} is Null-typed: it holds no typed value, "
                         f"so no total is taken over it - cast it to the type it holds")
    if not t.is_numeric():
        raise ValueError(f"control column {col!r} is {t}, not numeric: a cell in it did not "
                         f"read as a number, so no total is taken over it")
    s = df[col]
    nulls = s.null_count()
    if nulls:
        raise ValueError(f"control column {col!r} has {nulls} null cell(s) of {s.len()}: a "
                         f"cell the parse could not read, or a blank - no total is taken "
                         f"over the cells that did read; fix the parse, or fill a blank that "
                         f"means zero (`fill_null(0)`) and say so in the column's `parse`")
    if t.is_integer():
        return int(s.cast(pl.Int128).sum() or 0)
    if t.is_float():
        s = s.cast(pl.Float64)
        bad = int((s.is_nan() | s.is_infinite()).sum())
        if bad:
            raise ValueError(f"control column {col!r} has {bad} NaN or infinite cell(s): no "
                             f"total is taken over it")
        return round(math.fsum(s.to_list()), 4)
    exact = s.sum()                                # Decimal: exact
    exact = decimal.Decimal(0) if exact is None else decimal.Decimal(exact)
    v = round(float(exact), 4)
    if abs(decimal.Decimal(repr(v)) - exact) > decimal.Decimal("0.00005"):
        raise ValueError(f"control column {col!r} totals {exact}, which a float does not "
                         f"hold to 4 places ({v!r})")
    return v


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


STATED_FORM = ("`stated` is {\"value\": <the total the document states>, \"where\": "
               "\"<the page/line or cell that states it>\"}, and optionally \"tolerance\": "
               "<the largest difference that agrees, default 0.005>")


def _number(v, what: str) -> float:
    """A finite int, float, Decimal or numpy scalar as a float; anything else (a bool, a
    string) is refused."""
    if not isinstance(v, (int, float, str, bytes)) and hasattr(v, "item"):
        v = v.item()                               # a numpy scalar
    if isinstance(v, bool) or not isinstance(v, (int, float, decimal.Decimal)):
        raise ValueError(f"{what} {v!r} is not a number; {STATED_FORM}")
    try:
        x = float(v)
    except (OverflowError, ValueError):
        x = math.inf
    if not math.isfinite(x):
        raise ValueError(f"{what} {v!r} is not a finite number")
    return x


def _stated(stated, computed) -> dict | None:
    """The stated block: `value`, `where`, `computed`, `tolerance` and `agrees` (the two
    differ by no more than `tolerance`). Refused: not a dict, a key other than value /
    where / tolerance, no `where`, a `value` or `tolerance` that is not a finite number
    (int, float, Decimal or numpy scalar), a negative `tolerance`."""
    if stated is None:
        return None
    if not isinstance(stated, dict):
        raise ValueError(STATED_FORM)
    extra = sorted(str(k) for k in set(stated) - {"value", "where", "tolerance"})
    if extra:
        raise ValueError(f"`stated` has key(s) {extra} it does not take; {STATED_FORM}")
    where = stated.get("where")
    if not isinstance(where, str) or not where.strip():
        raise ValueError(STATED_FORM)
    value = _number(stated.get("value"), "`stated.value`")
    tol = _number(stated.get("tolerance", STATED_TOLERANCE), "`stated.tolerance`")
    if tol < 0:
        raise ValueError(f"`stated.tolerance` {tol!r} is negative")
    return {"value": value, "where": where.strip(), "computed": computed, "tolerance": tol,
            "agrees": abs(round(float(computed) - value, 4)) <= tol}


def write(run_dir, id: str, frame, *, file, source: str | None, file_role: str,
          header_at: str, rows: str, columns: dict, control: str | None,
          sheet: str | None = None, stated: dict | None = None, script=None,
          what: str | None = None) -> dict:
    """Cache one parsed table as `cache/<id>.parquet` with its manifest entry; returns the
    entry. An id written again is replaced. Everything is validated first, so a refused
    call changes nothing; then, under the cache's lock, the parquet is replaced and the
    manifest rewritten, each atomically. The entry records
    the parquet's own sha256 (`parquet_sha256`) for `verify`."""
    pl = _pl()
    run_dir = pathlib.Path(run_dir).resolve()
    if not isinstance(id, str) or not SLUG.fullmatch(id):
        raise ValueError(f"id {id!r} is not a slug ([a-z0-9][a-z0-9_-]*)")
    if file_role not in FILE_ROLES:
        raise ValueError(f"file_role {file_role!r}; one of {', '.join(sorted(FILE_ROLES))}")
    if hasattr(frame, "collect"):
        frame = frame.collect()
    if not isinstance(frame, pl.DataFrame):
        raise ValueError(f"frame is a {type(frame).__name__}, not a polars DataFrame")
    if frame.width == 0:
        raise ValueError(f"{id}: the frame has no columns")
    objects = [c for c in frame.columns if frame.schema[c] == pl.Object]
    if objects:
        raise ValueError(f"{id}: column(s) {objects} are Object-typed; a parquet holds typed "
                         f"columns only - cast each to the type it holds")
    path, sid, rel = resolve_file(run_dir, file, source)
    cols = _columns(frame, columns)
    if not isinstance(header_at, str) or not header_at.strip():
        raise ValueError("`header_at` is where the header sits: a cell (\"B4\"), \"line 5\", "
                         "\"p2:L3\" or \"none - columns by position\"")
    if frame.height and (not isinstance(rows, str) or not rows.strip()):
        raise ValueError("`rows` is the data rows as they sit in the file: \"5:40,42:1203\" "
                         "or \"p2:L7-15,p3:L4-12\"")
    if sheet is not None and (not isinstance(sheet, str) or not sheet.strip()):
        raise ValueError(f"{id}: `sheet` is the sheet's name as the workbook spells it, "
                         f"got {sheet!r}")
    if what is not None and (not isinstance(what, str) or not what.strip()):
        raise ValueError(f"{id}: `what` is the plan's words for the table, got {what!r}")
    if control is not None and control not in frame.columns:
        raise ValueError(f"control column {control!r} is not in the frame; it has "
                         f"{frame.columns}")
    total = control_value(frame, control)
    st = _stated(stated, total)
    if script is not None:
        sp = pathlib.Path(script)
        try:
            script = str(sp.resolve().relative_to(run_dir))
        except ValueError:
            script = str(sp)
    digest, size = _digest(path)
    out = run_dir / CACHE_DIR / f"{id}.parquet"
    tmp = _tmp_beside(out)
    try:
        frame.write_parquet(tmp)
        e = {"id": id, "what": what, "file": rel, "source": sid, "file_role": file_role,
             "sha256": digest, "bytes": size, "sheet": sheet,
             "header_at": header_at.strip(),
             "rows": rows.strip() if isinstance(rows, str) and rows.strip() else NO_ROWS,
             "columns": cols, "row_count": frame.height,
             "control_total": {"column": control, "value": total}}
        if st is not None:
            e["stated"] = st
        e.update({"parquet": f"{CACHE_DIR}/{id}.parquet", "parquet_sha256": sha256(tmp),
                  "script": script, "written_at": _now()})
        with _locked(run_dir):
            man = manifest(run_dir)                # refuses a foreign manifest first
            tmp.replace(out)
            man["files"] = [x for x in man["files"] if x["id"] != id] + [e]
            _save(run_dir, man)
    finally:
        tmp.unlink(missing_ok=True)
    return e


def note(run_dir, file, *, where: str, what: str, source: str | None = None) -> dict:
    """Record a table on a file that no downstream step needs, so it is seen and not
    extracted: `where` (`"Summary!G24:K41"`, `"p4:L1-30"`), `what` in words. The same
    file and `where` noted again is replaced. `file` is a string or a path; `where` and
    `what` are non-empty strings."""
    for k, v, types in (("file", file, (str, pathlib.PurePath)), ("where", where, str),
                        ("what", what, str)):
        if not isinstance(v, types) or not str(v).strip():
            raise ValueError(f"`{k}` is required")
    n = {"file": str(file), "source": source, "where": where.strip(), "what": what.strip()}
    with _locked(run_dir):
        man = manifest(run_dir)
        man["not_extracted"] = [x for x in man["not_extracted"]
                                if (x.get("file"), x.get("source"), x.get("where"))
                                != (n["file"], source, n["where"])] + [n]
        _save(run_dir, man)
    return n


# ---------------------------------------------------------------- the exact re-check

def verify(run_dir, id: str | None = None) -> list[dict]:
    """Per id, `{id, agrees, why}`: the source file exists with the cached sha256 and
    bytes, the parquet has the sha256 recorded when it was written (so its content is the
    frame the entry describes), and it holds the recorded row count. Nothing is
    re-parsed. A source or parquet that cannot be found or read is a disagreement with its
    reason. `why` is None when it agrees."""
    pl = _pl()
    run_dir = pathlib.Path(run_dir).resolve()
    ents = [entry(run_dir, id)] if id is not None else manifest(run_dir)["files"]
    out = []
    for e in ents:
        why = None
        try:
            path, _, _ = resolve_file(run_dir, e["file"], e.get("source"))
            digest, size = _digest(path)
        except (ValueError, OSError) as exc:
            why = f"the source file: {exc}"
        else:
            if size != e.get("bytes"):
                why = f"the source file changed: {size} bytes, cached {e.get('bytes')}"
            elif digest != e.get("sha256"):
                why = "the source file changed: its sha256 differs from the cached one"
        if why is None:
            pq = run_dir / e["parquet"]
            if not pq.is_file():
                why = f"parquet missing: {pq}"
            else:
                try:
                    if sha256(pq) != e.get("parquet_sha256"):
                        why = ("the parquet changed after it was written: its sha256 "
                               "differs from the manifest's")
                    else:
                        n = pl.scan_parquet(pq).select(pl.len()).collect().item()
                        if n != e["row_count"]:
                            why = f"the parquet holds {n} rows, the manifest {e['row_count']}"
                except (OSError, pl.exceptions.PolarsError) as exc:
                    why = f"parquet unreadable: {str(exc).splitlines()[0] if str(exc) else exc!r}"
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
    return _cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
