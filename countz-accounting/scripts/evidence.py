#!/usr/bin/env python3
"""A `span` citation (EVIDENCE.md § 1) that falls out of the read, measured on the file.

In a step's code:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from evidence import select, span, write_ledger

    rows, e = select(RUN, "SELECT customer_id, invoice_amount FROM invoice_lines_fy2025 "
                          "WHERE stream = 'subscription'",
                     id="E.a4.sub_lines", control="invoice_amount", note="...")
    write_ledger(RUN / "workpapers/evidence-a4_cube.yaml", [e])
    total = rows["invoice_amount"].sum()          # the figure's arithmetic, in code

`select()` is the read. One SQL statement over one cache id (a table name in
`cache/manifest.json`) returns the rows and the citation of the same rows: `file`,
`source`, `file_role`, `header_at`, the columns (letter and parse) and the `rows` come from
the manifest; `filter` is the WHERE clause verbatim, in the file's own column names;
`row_count` and `control_total` are measured over the rows returned. The two cannot
disagree because there is one query. A span cites one table: a JOIN, a GROUP BY, a
subquery or a computed column is refused — select the source columns, then aggregate
or join in polars over the rows, and let the figure's `expression` carry that
arithmetic. A join across two files is two spans. A column is named as the file's header
names it: bare (`invoice_amount`, `Débit`) or double-quoted where it carries punctuation
(`"Amount (USD)"`); a quoted string in the WHERE clause is a value, whatever words it holds.
The span's `rows` are the manifest's — the block as cut, never recomputed from a count.

`span()` is the same citation for a read the cache did not serve. `what` is a cache id
(with `run_dir`), or a run artifact under `checks/` — the run's own CSV item tables, read
by polars as written (`file_role: run_artifact`, `from_check` from the file name unless
given). A data-room file is never parsed here: a step that parses one itself passes the
frame and the coordinates it read it at — `span(frame=df, file=..., source=...,
file_role=..., sheet=..., header_at=..., rows=..., columns={name: {"at": ..., "parse":
...}})` — and the entry is measured over that frame. `filter` is a polars SQL WHERE clause
or a `pl.Expr`, recorded verbatim. With `reperform`, a cache id is first re-checked by
`cache.verify` (the source file's sha256 and bytes, the parquet's row count) and a
disagreement raises CacheDefect. `header_at`, `rows`, `holds`, `parse` and `filter` are
always set; with no filter the entry states `none - full sheet consumed`.

Command line, printing the entry as YAML:

    evidence.py select "<sql>" --run-dir <run_dir> [--id E.x.y] [--control amount]
        [--note "..."] [--reperform]
    evidence.py span <cache id | checks/ path> [--run-dir <run_dir>] [--id E.x.y]
        [--columns a,b] [--control amount] [--filter "<sql where>"] [--from-check c1]
        [--note "..."] [--reperform]

Requires polars and pyyaml — run as `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cache  # noqa: E402  sibling: the cache and its manifest

ROLES = cache.FILE_ROLES | {"run_artifact"}
AS_WRITTEN = "as written"
NO_FILTER = "none - full sheet consumed"


def _today() -> str:
    return datetime.date.today().isoformat()


def _apply_filter(df, flt):
    pl = cache._pl()
    if flt is None or (isinstance(flt, str) and not flt.strip()):
        return df, NO_FILTER
    if isinstance(flt, str):
        return df.filter(pl.sql_expr(flt)), flt.strip()
    return df.filter(flt), str(flt)


def _columns(df, names, cols: dict[str, dict]) -> list[dict]:
    names = list(names) if names else list(df.columns)
    missing = [n for n in names if n not in df.columns]
    if missing:
        raise ValueError(f"columns not in the file: {missing}; it has {df.columns}")
    return [{"name": n, "at": cols[n]["at"], "holds": "values", "parse": cols[n]["parse"]}
            for n in names]


def _from_cache(run_dir: pathlib.Path, file_id: str) -> tuple[dict, "object", dict[str, dict]]:
    e = cache.entry(run_dir, file_id)
    return e, cache.read(run_dir, file_id), _manifest_columns(e)


def _manifest_columns(e: dict) -> dict[str, dict]:
    return {c["name"]: {"at": c["at"], "parse": c.get("parse") or AS_WRITTEN}
            for c in e["columns"]}


def _artifact(run_dir: pathlib.Path | None, what) -> pathlib.Path | None:
    """The path of a run artifact under `<run_dir>/checks/`, or None."""
    p = pathlib.Path(str(what))
    if run_dir is None:
        return None
    if not p.is_absolute():
        p = run_dir / p
    try:
        inside = p.resolve().relative_to(run_dir)
    except ValueError:
        return None
    return p.resolve() if inside.parts[:1] == ("checks",) and p.is_file() else None


def _from_artifact(run_dir: pathlib.Path, path: pathlib.Path) -> tuple[dict, "object", dict[str, dict]]:
    """A run artifact: the run's own item table (`items.py`), read as it was written -
    ids and extensions as text, `amount` as a number."""
    import items
    check, _, name = path.stem.partition("-")
    if path.suffix.lower() != ".csv" or not name:
        raise ValueError(f"{path.name}: a run artifact span reads an item table "
                         f"`checks/<check>-<table>.csv`; cite any other read with `frame=`")
    df = items.read_items(run_dir, check, name, frame=True)
    cols = {c: {"at": _col_letter(i + 1), "parse": AS_WRITTEN}
            for i, c in enumerate(df.columns)}
    e = {"id": None, "source": None, "file": str(path.relative_to(run_dir)),
         "file_role": "run_artifact", "sheet": None, "header_at": "A1",
         "rows": f"2:{df.height + 1}" if df.height else cache.NO_ROWS}
    return e, df, cols


def _col_letter(i: int) -> str:
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _from_frame(frame, run_dir: pathlib.Path | None, file, source, file_role, sheet,
                header_at_, rows, columns) -> tuple[dict, "object", dict[str, dict]]:
    """A data-room table the step parsed itself: the coordinates are the step's."""
    pl = cache._pl()
    if hasattr(frame, "collect"):
        frame = frame.collect()
    if not isinstance(frame, pl.DataFrame):
        raise ValueError(f"frame is a {type(frame).__name__}, not a polars DataFrame")
    if file_role not in cache.FILE_ROLES:
        raise ValueError(f"file_role {file_role!r}; a data-room file is one of "
                         f"{', '.join(sorted(cache.FILE_ROLES))}")
    if run_dir is not None:
        _, sid, rel = cache.resolve_file(run_dir, file, source)
    else:
        p = pathlib.Path(str(file or ""))
        if not str(file or "").strip() or not p.is_file():
            raise ValueError(f"file missing: {file!r} - pass run_dir to resolve a path "
                             f"relative to its source")
        sid, rel = source, str(p)
    if not isinstance(header_at_, str) or not header_at_.strip():
        raise ValueError("`header_at` is where the header sits in the file: a cell (\"B4\"), "
                         "\"line 5\", \"p2:L3\" or \"none - columns by position\"")
    if frame.height and (not isinstance(rows, str) or not rows.strip()):
        raise ValueError("`rows` is the data rows as they sit in the file: \"5:40,42:1203\" "
                         "or \"p2:L7-15,p3:L4-12\"")
    if not isinstance(columns, dict) or not columns:
        raise ValueError("`columns` maps each column cited to {\"at\": <letter or chars "
                         "41-50>, \"parse\": <how its text was read>}")
    cols = {}
    for n, spec in columns.items():
        if n not in frame.columns:
            raise ValueError(f"column {n!r} is not in the frame; it has {frame.columns}")
        bad = [k for k in ("at", "parse") if not isinstance(spec, dict)
               or not isinstance(spec.get(k), str) or not spec[k].strip()]
        if bad:
            raise ValueError(f"column {n!r}: no {' / '.join(bad)}")
        cols[n] = {"at": spec["at"].strip(), "parse": spec["parse"].strip()}
    e = {"id": None, "source": sid, "file": rel, "file_role": file_role, "sheet": sheet,
         "header_at": header_at_.strip(),
         "rows": rows.strip() if isinstance(rows, str) and rows.strip() else cache.NO_ROWS}
    return e, frame, cols


# One table, plain rows: `SELECT <cols | *> FROM <cache id> [WHERE ...] [ORDER BY ...]
# [LIMIT n]`. Anything that would make the rows other than the file's rows is refused.
SELECT = re.compile(r"^\s*SELECT\s+(?P<cols>.+?)\s+FROM\s+(?P<table>[A-Za-z0-9_-]+)"
                    r"(?:\s+WHERE\s+(?P<where>.+?))?"
                    r"(?:\s+ORDER\s+BY\s+.+?)?(?:\s+LIMIT\s+\d+)?\s*;?\s*$",
                    re.I | re.S)
REFUSED = re.compile(r"\b(JOIN|GROUP\s+BY|HAVING|UNION|DISTINCT|WITH)\b|\(\s*SELECT\b", re.I)
# A quoted string or a quoted identifier: blanked before the statement's shape is read,
# so a memo that says `PAID WITH CHECK` is a value, not a WITH clause.
QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
# A column as a span selects it: a quoted identifier (any characters the file's header
# has, `"Amount (USD)"`), or a bare name in letters, digits, underscores and spaces.
COLUMN = re.compile(r'^(?:"(?P<q>(?:[^"]|"")+)"|(?P<b>[^\W\d][\w ]*))$')


def _blank_quoted(sql: str) -> str:
    return QUOTED.sub(lambda m: m.group(0)[0] + " " * (len(m.group(0)) - 2) + m.group(0)[-1],
                      sql)


def _split_columns(cols: str) -> list[str]:
    out, cur, quoted = [], "", False
    for ch in cols:
        if ch == '"':
            quoted = not quoted
        if ch == "," and not quoted:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return out


def header_at(e: dict) -> str:
    """Where the header is, as the manifest states it: a cell (`A4`), `line 5`, `p2:L3`,
    or `none - columns by position`."""
    if not e.get("header_at"):
        raise ValueError(f"{e.get('id')}: the manifest entry states no `header_at`; re-run "
                         f"the extract step's script")
    return e["header_at"]


_header_at = header_at        # span()'s `header_at` parameter shadows the name


def cited_rows(e: dict) -> str:
    """The block's rows as the manifest states them: sheet rows (`6:1204`), or a PDF's
    page and line ranges (`p2:L7-15,p3:L4-12`)."""
    if e.get("rows") is None:
        raise ValueError(f"{e.get('id')}: the manifest entry states no `rows`; re-run "
                         f"the extract step's script")
    return e["rows"]


def _parse_select(sql: str) -> tuple[str, list[str] | None, str | None]:
    """(table, selected column names or None for *, where text or None)."""
    shape = _blank_quoted(sql)
    if REFUSED.search(shape):
        raise ValueError("a span cites one table's rows: no JOIN, GROUP BY, HAVING, UNION, "
                         "DISTINCT, WITH or subquery - select the source columns and "
                         "aggregate or join in polars over the rows returned")
    m = SELECT.match(shape)
    if not m:
        raise ValueError("the statement is `SELECT <columns | *> FROM <cache id> "
                         "[WHERE ...] [ORDER BY ...] [LIMIT n]`")
    cols = sql[m.start("cols"):m.end("cols")].strip()
    if cols == "*":
        names = None
    else:
        names = []
        for c in _split_columns(cols):
            mc = COLUMN.match(c)
            if not mc or (mc.group("b") and re.search(r"\bAS\b", c, re.I)):
                raise ValueError(f"column `{c}`: a span selects source columns by name, "
                                 f"unaliased and uncomputed - quote a name with "
                                 f"punctuation (\"Amount (USD)\"); compute over the rows "
                                 f"returned")
            names.append(mc.group("q").replace('""', '"') if mc.group("q")
                         else mc.group("b").strip())
    where = sql[m.start("where"):m.end("where")] if m.group("where") else None
    return m.group("table"), names, where.strip() if where else None


def select(run_dir, sql: str, *, id: str | None = None, control: str | None = None,
           note: str | None = None, read_at: str | None = None,
           reperform: bool = False):
    """Run one SELECT over one cache id; return (rows, span entry) for those rows."""
    pl = cache._pl()
    run_dir = pathlib.Path(run_dir).resolve()
    table, names, where = _parse_select(sql)
    e = cache.entry(run_dir, table)
    if reperform:
        _reperform(run_dir, table)
    letters = _manifest_columns(e)
    if names:
        missing = [n for n in names if n not in letters]
        if missing:
            raise ValueError(f"columns not in {table}: {missing}; it has {list(letters)}")
    ctx = pl.SQLContext(**{table: pl.scan_parquet(run_dir / e["parquet"])})
    try:
        rows = ctx.execute(sql).collect()
    except Exception as exc:
        raise ValueError(f"the statement did not run: {str(exc).splitlines()[0]}; "
                         f"{table}'s columns are {list(letters)}") from exc
    role = e.get("file_role")
    if role not in ROLES:
        raise ValueError(f"{table}: the manifest entry has no file_role (one of "
                         f"{', '.join(sorted(ROLES))})")
    ctl = control or (e.get("control_total") or {}).get("column")
    if ctl is None:
        value: float | int = rows.height
        ctl_name = "rows"
    else:
        if ctl not in letters:
            raise ValueError(f"control column {ctl!r} is not in {table}")
        if ctl in rows.columns:
            value = cache.control_value(rows, ctl)
        else:                                       # the control column over the same rows
            quoted = ctl.replace('"', '""')
            q = f'SELECT "{quoted}" FROM {table}' + (f" WHERE {where}" if where else "")
            value = cache.control_value(ctx.execute(q).collect(), ctl)
        ctl_name = ctl
    entry = {"id": id, "kind": "span", "file": e["file"], "source": e.get("source"),
             "file_role": role, "sheet": e.get("sheet"), "header_at": header_at(e),
             "rows": cited_rows(e),
             "columns": [{"name": n, "at": letters[n]["at"], "holds": "values",
                          "parse": letters[n]["parse"]} for n in rows.columns],
             "filter": where or NO_FILTER, "row_count": rows.height,
             "control_total": {"column": ctl_name, "value": value},
             "value_source": "cell_values", "read_at": read_at or _today()}
    if note:
        entry["note"] = note
    return rows, entry


class CacheDefect(ValueError):
    """The cache disagrees with its source (`reperform`): the reader records it and
    reads the source instead (agents/worker.md § Your procedure)."""


def _reperform(run_dir: pathlib.Path, table: str) -> None:
    r = cache.verify(run_dir, table)[0]
    if not r["agrees"]:
        raise CacheDefect(f"cache id {table!r}: {r['why']}")


def span(what=None, *, run_dir=None, frame=None, file=None, id: str | None = None,
         source: str | None = None, file_role: str | None = None, sheet: str | None = None,
         header_at: str | None = None, rows: str | None = None, columns=None,
         control: str | None = None, filter=None, note: str | None = None,
         from_check: str | None = None, read_at: str | None = None,
         reperform: bool = False) -> dict:
    """One measured span entry. `what` is a cache id (with `run_dir`; `columns` a list of
    the names consumed) or a run artifact under `<run_dir>/checks/`. With `frame`, the
    step parsed a data-room file itself: `file`, `source`, `file_role`, `sheet`,
    `header_at`, `rows` and `columns` ({name: {"at", "parse"}}, the columns cited) are
    the step's coordinates, and `row_count` / `control_total` are measured over the frame
    after `filter`. A data-room path with no frame is refused — this module parses no
    client file. With `reperform`, a cache read first runs `cache.verify` and raises
    CacheDefect on a disagreement. With no `control` and none on the manifest, the
    control total is the row count."""
    run_dir = pathlib.Path(run_dir).resolve() if run_dir else None
    if frame is not None:
        if what is not None:
            raise ValueError("pass `what` (a cache id or a checks/ path) or `frame`, not both")
        e, df, cols = _from_frame(frame, run_dir, file, source, file_role, sheet,
                                  header_at, rows, columns)
        names = list(cols)
    else:
        art = _artifact(run_dir, what) if what is not None else None
        if art is not None:
            e, df, cols = _from_artifact(run_dir, art)
        elif run_dir is not None and what is not None \
                and str(what) in {x["id"] for x in cache.manifest(run_dir)["files"]}:
            e, df, cols = _from_cache(run_dir, str(what))
            if reperform:
                _reperform(run_dir, str(what))
        elif what is not None and pathlib.Path(str(what)).is_file():
            raise ValueError(f"{what}: a data-room file is not parsed here - parse it in "
                             f"the step and pass `frame=` with its coordinates, or read "
                             f"the cache by id")
        else:
            raise ValueError(f"{what!r} is neither a cache id in "
                             f"{run_dir}/cache/manifest.json nor a run artifact under "
                             f"checks/" if run_dir else
                             f"{what!r}: a cache id or a checks/ path needs `run_dir`")
        names = columns
    role = file_role or e.get("file_role")
    if role == "run_artifact" and not from_check:
        from_check = pathlib.Path(e["file"]).stem.split("-", 1)[0]
    if role not in ROLES:
        raise ValueError(f"file_role {role!r}; one of {', '.join(sorted(ROLES))}")
    rows_ = cited_rows(e)
    try:
        kept, flt_text = _apply_filter(df, filter)
    except Exception as exc:                          # a polars error names the column
        raise ValueError(f"filter {filter!r} did not apply: {str(exc).splitlines()[0]}; "
                         f"the file's columns are {df.columns}") from exc
    ctl = control or (e.get("control_total") or {}).get("column")
    if ctl is not None and ctl not in kept.columns:
        raise ValueError(f"control column {ctl!r} is not in the file; it has {df.columns}")
    entry = {
        "id": id,
        "kind": "span",
        "file": e["file"],
        "source": e.get("source"),
        "file_role": role,
    }
    if role == "run_artifact":
        entry["from_check"] = from_check
    entry.update({
        "sheet": e.get("sheet"),
        "header_at": _header_at(e),
        "rows": rows_,
        "columns": _columns(kept, names, cols),
        "filter": flt_text,
        "row_count": kept.height,
        "control_total": {"column": ctl if ctl is not None else "rows",
                          "value": cache.control_value(kept, ctl)},
        "value_source": "cell_values",
        "read_at": read_at or _today(),
    })
    if note:
        entry["note"] = note
    return entry


def write_ledger(path, entries: list[dict], merge: bool = True) -> pathlib.Path:
    """Write entries to a `workpapers/*.yaml` ledger as the YAML list EVIDENCE.md § 0
    requires. With `merge`, an existing ledger's entries are kept and an entry with the
    same id is replaced."""
    import yaml
    path = pathlib.Path(path)
    for e in entries:
        if not e.get("id"):
            raise ValueError("every ledger entry carries an id")
    kept: dict[str, dict] = {}
    if merge and path.is_file():
        prior = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(prior, list):
            raise ValueError(f"{path}: the ledger is not a YAML list")
        for e in prior:
            kept[e["id"]] = e
    for e in entries:
        kept[e["id"]] = e
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(list(kept.values()), sort_keys=False,
                                  allow_unicode=True, width=100), encoding="utf-8")
    tmp.replace(path)
    return path


def main() -> int:
    import yaml
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("select", help="run one SELECT over a cache id; print its span entry")
    q.add_argument("sql")
    q.add_argument("--run-dir", type=pathlib.Path, required=True)
    q.add_argument("--id")
    q.add_argument("--control")
    q.add_argument("--note")
    q.add_argument("--reperform", action="store_true")
    s = sub.add_parser("span", help="print one measured span entry as YAML")
    s.add_argument("what", help="a cache id, or a run artifact under checks/")
    s.add_argument("--run-dir", type=pathlib.Path, required=True)
    s.add_argument("--id")
    s.add_argument("--columns", help="comma-separated column names consumed")
    s.add_argument("--control", help="the control-total column")
    s.add_argument("--filter", help="a polars SQL WHERE clause")
    s.add_argument("--from-check")
    s.add_argument("--note")
    s.add_argument("--reperform", action="store_true",
                   help="re-check the cached id's source first; exit 3 on a cache defect")
    a = ap.parse_args()
    if a.cmd == "select":
        try:
            rows, e = select(a.run_dir, a.sql, id=a.id, control=a.control, note=a.note,
                             reperform=a.reperform)
        except CacheDefect as exc:
            print(f"CACHE DEFECT: {exc}", file=sys.stderr)
            return 3
        except (ValueError, KeyError) as exc:
            print(f"evidence.py: {exc}", file=sys.stderr)
            return 1
        print(yaml.safe_dump([e], sort_keys=False, allow_unicode=True, width=100), end="")
        print(f"# {rows.height} row(s) returned", file=sys.stderr)
        return 0
    try:
        e = span(a.what, run_dir=a.run_dir, id=a.id,
                 columns=[c for c in (a.columns or "").split(",") if c], control=a.control,
                 filter=a.filter, note=a.note, from_check=a.from_check,
                 reperform=a.reperform)
    except CacheDefect as exc:
        print(f"CACHE DEFECT: {exc}", file=sys.stderr)
        return 3
    except (ValueError, KeyError) as exc:
        print(f"evidence.py: {exc}", file=sys.stderr)
        return 1
    print(yaml.safe_dump([e], sort_keys=False, allow_unicode=True, width=100), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
