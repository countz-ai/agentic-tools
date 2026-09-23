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
`source`, `file_role`, `header_at`, the column letters and the block's `rows` come from
the manifest; `filter` is the WHERE clause verbatim, in the file's own column names;
`row_count` and `control_total` are measured over the rows returned. The two cannot
disagree because there is one query. A span cites one table: a JOIN, a GROUP BY, a
subquery or a computed column is refused — select the source columns, then aggregate
or join in polars over the rows, and let the figure's `expression` carry that
arithmetic. A join across two files is two spans.

`span()` is the same citation for a read the cache did not serve: a path to a data-room
file (read as extract.py reads it, header detected) or to a run artifact under
`checks/` (`file_role: run_artifact`, `from_check` from the file name unless given);
`filter` is a polars SQL WHERE clause or a `pl.Expr`. With `reperform`, a cache id is
first re-read from its source and a disagreement raises CacheDefect. `header_at`,
`rows`, `holds` and `filter` are always set; with no filter the entry states
`none - full sheet consumed`.

Command line, printing the entry as YAML:

    evidence.py select "<sql>" --run-dir <run_dir> [--id E.x.y] [--control amount]
        [--note "..."]
    evidence.py span <cache id | path> [--run-dir <run_dir>] [--id E.x.y] [--source gl]
        [--role system_export] [--columns a,b] [--control amount]
        [--filter "<sql where>"] [--from-check c1] [--note "..."] [--reperform]

Requires polars and pyyaml — run as `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import extract  # noqa: E402  sibling: the cache, its manifest, and the header detector

ROLES = {"system_export", "management_prepared", "bank_statement", "policy_document",
         "correspondence", "unknown", "run_artifact"}
NO_FILTER = "none - full sheet consumed"


def _today() -> str:
    return datetime.date.today().isoformat()


def _apply_filter(df, flt):
    pl = extract._pl()
    if flt is None or (isinstance(flt, str) and not flt.strip()):
        return df, NO_FILTER
    if isinstance(flt, str):
        return df.filter(pl.sql_expr(flt)), flt.strip()
    return df.filter(flt), str(flt)


def _columns(df, names, letters: dict[str, str]) -> list[dict]:
    names = list(names) if names else list(df.columns)
    missing = [n for n in names if n not in df.columns]
    if missing:
        raise ValueError(f"columns not in the file: {missing}; it has {df.columns}")
    return [{"name": n, "at": letters[n], "holds": "values"} for n in names]


def _from_cache(run_dir: pathlib.Path, file_id: str) -> tuple[dict, "object", dict[str, str]]:
    e = extract.entry(run_dir, file_id)
    df = extract.read(run_dir, file_id)
    letters = {c["name"]: c["at"] for c in e["columns"]}
    return e, df, letters


def _from_path(path: pathlib.Path, run_dir: pathlib.Path | None, source: str | None,
               header_row: int | None, sheet: str | None) -> tuple[dict, "object", dict[str, str]]:
    spec = {"header_row": header_row, "sheet": sheet}
    df, facts = extract.load_frame(path, spec)
    letters = {c: extract.col_letter(i + 1) for i, c in enumerate(df.columns)}
    rel, sid, role = str(path), source, None
    if run_dir is not None and (run_dir / "run.json").is_file():
        sources = extract.sources_by_id(extract.load_run(run_dir))
        try:
            p, sid, rel = extract.resolve_path({"path": str(path), "source": source}, sources)
        except ValueError:
            pass
        try:
            inside = path.resolve().relative_to(run_dir.resolve())
            if inside.parts and inside.parts[0] in ("checks", "workpapers", "out"):
                rel, role, sid = str(inside), "run_artifact", None
        except ValueError:
            pass
    e = {"id": None, "source": sid, "file": rel, "file_role": role, "sheet": facts["sheet"],
         "header_row": facts["header_row"], "row_count": df.height}
    return e, df, letters


# One table, plain rows: `SELECT <cols | *> FROM <cache id> [WHERE ...] [ORDER BY ...]
# [LIMIT n]`. Anything that would make the rows other than the file's rows is refused.
SELECT = re.compile(r"^\s*SELECT\s+(?P<cols>.+?)\s+FROM\s+(?P<table>[A-Za-z0-9_-]+)"
                    r"(?:\s+WHERE\s+(?P<where>.+?))?"
                    r"(?:\s+ORDER\s+BY\s+.+?)?(?:\s+LIMIT\s+\d+)?\s*;?\s*$",
                    re.I | re.S)
REFUSED = re.compile(r"\b(JOIN|GROUP\s+BY|HAVING|UNION|DISTINCT|WITH)\b|\(\s*SELECT\b", re.I)


def _parse_select(sql: str) -> tuple[str, list[str] | None, str | None]:
    """(table, selected column names or None for *, where text or None)."""
    if REFUSED.search(sql):
        raise ValueError("a span cites one table's rows: no JOIN, GROUP BY, HAVING, UNION, "
                         "DISTINCT, WITH or subquery - select the source columns and "
                         "aggregate or join in polars over the rows returned")
    m = SELECT.match(sql)
    if not m:
        raise ValueError("the statement is `SELECT <columns | *> FROM <cache id> "
                         "[WHERE ...] [ORDER BY ...] [LIMIT n]`")
    cols = m.group("cols").strip()
    if cols == "*":
        names = None
    else:
        names = []
        for c in cols.split(","):
            c = c.strip().strip('"')
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ ]*", c):
                raise ValueError(f"column `{c}`: a span selects source columns by name, "
                                 f"unaliased and uncomputed; compute over the rows returned")
            names.append(c)
    where = m.group("where")
    return m.group("table"), names, where.strip() if where else None


def select(run_dir, sql: str, *, id: str | None = None, control: str | None = None,
           note: str | None = None, read_at: str | None = None,
           reperform: bool = False):
    """Run one SELECT over one cache id; return (rows, span entry) for those rows."""
    pl = extract._pl()
    run_dir = pathlib.Path(run_dir).resolve()
    table, names, where = _parse_select(sql)
    e = extract.entry(run_dir, table)
    if reperform:
        r = extract.reperform(run_dir, table)
        if not r["agrees"]:
            raise CacheDefect(f"cache id {table!r}: {r.get('why')} - {r}")
    letters = {c["name"]: c["at"] for c in e["columns"]}
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
        raise ValueError(f"{table}: the extract spec set no file_role (one of "
                         f"{', '.join(sorted(ROLES))})")
    ctl = control or (e.get("control_total") or {}).get("column")
    if ctl is None:
        value: float | int = rows.height
        ctl_name = "rows"
    else:
        if ctl not in letters:
            raise ValueError(f"control column {ctl!r} is not in {table}")
        if ctl in rows.columns:
            value = extract.control_value(rows, ctl)
        else:                                       # the control column over the same rows
            q = f"SELECT \"{ctl}\" FROM {table}" + (f" WHERE {where}" if where else "")
            value = extract.control_value(ctx.execute(q).collect(), ctl)
        ctl_name = ctl
    header_row = int(e["header_row"])
    entry = {"id": id, "kind": "span", "file": e["file"], "source": e.get("source"),
             "file_role": role, "sheet": e.get("sheet"), "header_at": f"A{header_row}",
             "rows": e.get("rows") or f"{header_row + 1}:{header_row + int(e['row_count'])}",
             "columns": [{"name": n, "at": letters[n], "holds": "values"} for n in rows.columns],
             "filter": where or NO_FILTER, "row_count": rows.height,
             "control_total": {"column": ctl_name, "value": value},
             "value_source": "cell_values", "read_at": read_at or _today()}
    if note:
        entry["note"] = note
    return rows, entry


class CacheDefect(ValueError):
    """The cache disagrees with its source (`reperform`): the reader records it and
    reads the source instead (agents/worker.md § Your procedure)."""


def span(what, *, run_dir=None, id: str | None = None, source: str | None = None,
         file_role: str | None = None, columns=None, control: str | None = None,
         filter=None, note: str | None = None, from_check: str | None = None,
         header_row: int | None = None, sheet: str | None = None,
         read_at: str | None = None, reperform: bool = False) -> dict:
    """One measured span entry. `what` is a cache id (with `run_dir`) or a path. With
    `reperform`, a cache read first re-reads the source block and raises CacheDefect
    when the file, row count or control total no longer agree with the manifest."""
    run_dir = pathlib.Path(run_dir).resolve() if run_dir else None
    as_path = pathlib.Path(str(what))
    if run_dir is not None and not as_path.is_file():
        try:
            e, df, letters = _from_cache(run_dir, str(what))
        except KeyError as exc:
            raise ValueError(f"{what!r} is neither a cache id in {run_dir}/cache/manifest.json "
                             f"nor a file") from exc
        if reperform:
            r = extract.reperform(run_dir, str(what))
            if not r["agrees"]:
                raise CacheDefect(f"cache id {what!r}: {r.get('why')} - {r}")
    else:
        if not as_path.is_file():
            raise ValueError(f"not a file: {as_path}")
        e, df, letters = _from_path(as_path, run_dir, source, header_row, sheet)
    role = file_role or e.get("file_role")
    if role == "run_artifact" and not from_check:
        from_check = pathlib.Path(e["file"]).stem.split("-", 1)[0]
    if role not in ROLES:
        raise ValueError(f"file_role {role!r}; one of {', '.join(sorted(ROLES))} "
                         f"(the manifest carries it when the extract spec set it)")
    header_row_ = int(e["header_row"])
    block_rows = int(e["row_count"])
    try:
        kept, flt_text = _apply_filter(df, filter)
    except Exception as exc:                          # a polars error names the column
        raise ValueError(f"filter {filter!r} did not apply: {str(exc).splitlines()[0]}; "
                         f"the file's columns are {df.columns}") from exc
    ctl = control or (e.get("control_total") or {}).get("column") \
        or extract.pick_control(df, None)
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
        "header_at": f"A{header_row_}",
        "rows": f"{header_row_ + 1}:{header_row_ + block_rows}",
        "columns": _columns(kept, columns, letters),
        "filter": flt_text,
        "row_count": kept.height,
        "control_total": {"column": ctl if ctl is not None else "rows",
                          "value": extract.control_value(kept, ctl)},
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
        prior = yaml.safe_load(path.read_text()) or []
        if not isinstance(prior, list):
            raise ValueError(f"{path}: the ledger is not a YAML list")
        for e in prior:
            kept[e["id"]] = e
    for e in entries:
        kept[e["id"]] = e
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(list(kept.values()), sort_keys=False,
                                  allow_unicode=True, width=100))
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
    s.add_argument("what", help="a cache id (with --run-dir) or a file path")
    s.add_argument("--run-dir", type=pathlib.Path)
    s.add_argument("--id")
    s.add_argument("--source")
    s.add_argument("--role", choices=sorted(ROLES))
    s.add_argument("--columns", help="comma-separated column names consumed")
    s.add_argument("--control", help="the control-total column")
    s.add_argument("--filter", help="a polars SQL WHERE clause")
    s.add_argument("--from-check")
    s.add_argument("--header-row", type=int)
    s.add_argument("--sheet")
    s.add_argument("--note")
    s.add_argument("--reperform", action="store_true",
                   help="re-read the source block first; exit 3 on a cache defect")
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
        e = span(a.what, run_dir=a.run_dir, id=a.id, source=a.source, file_role=a.role,
                 columns=[c for c in (a.columns or "").split(",") if c], control=a.control,
                 filter=a.filter, note=a.note, from_check=a.from_check,
                 header_row=a.header_row, sheet=a.sheet, reperform=a.reperform)
    except CacheDefect as exc:
        print(f"CACHE DEFECT: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"evidence.py: {exc}", file=sys.stderr)
        return 1
    print(yaml.safe_dump([e], sort_keys=False, allow_unicode=True, width=100), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
