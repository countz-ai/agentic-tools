#!/usr/bin/env python3
"""The workbook's ledger tabs, written from the run's records and never by hand: Sources
(one row per figure and population), Tables (one row per table, then the constants) and
Evidence (one row per read of a file). They are the trail a reader follows down from a
number (docs/REPERFORM.md): a figure's Sources row shows its statement and what it reads,
each table's Tables row shows what one row of it is, the statement that made it, what it
reads and the counts a re-run is compared against, and each data-room table lands on its
Evidence row.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from ledger_tabs import write
    write(wb, RUN, "Sablewood Analytics, Inc. · Contract costs, December 31, 2024 and 2025")

`write` appends the three tabs to `wb` in that order, after every other tab, replacing any
of the same name. It refuses, writing nothing, when the figure ledgers disagree on an id
or resolve_roots.py refuses a ledger record: both are the owning check's to fix.

Sources columns: id | label | value | unit | disposition | expression | reads | root
source | To reperform | population | caveats and carry-forwards | from check. `reads` is
what the entry's statement reads, one per cell: the tables, figures and constants for a
figure computed in SQL, the ledger inputs for any other. `root source` is where it lands
once every hop is collapsed (resolve_roots.py). `To reperform` for a SQL figure is the
expression run over its reads, with the value it gives; for any other it is the reads,
the arithmetic and the expected value.

Tables columns: table | what one row is | made by | rows | totals | result hash | SQL or
read | evidence | reads. `totals` sums every DECIMAL and DOUBLE column over all rows, to
the cent. `result hash` is the one `countz-sql` prints for `SELECT * FROM <table>`, given
when the table has ten rows or more, as the console prints it only then. For a table read
from the data room, the read (file, sheet, header, rows, control total) stands in the SQL
column and `evidence` names its Evidence row. The Constants table follows: name | value |
unit | kind | where | quote or basis | evidence.

Run with `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import figures as _figures  # noqa: E402  sibling: the ledgers and the number formatter
from wbkit import (FMT_CENTS, FMT_COUNT, FMT_DAYS, FMT_FX, FMT_PCT, FMT_RATE, S, WRAP,  # noqa: E402
                   band, bind_styles, finish, get_column_letter, header, ident, next_block,
                   section, text)

SOURCES, TABLES, EVIDENCE = "Sources", "Tables", "Evidence"
VALUE_FORMAT = {"pct": FMT_PCT, "count": FMT_COUNT, "ratio": "0.00", "fx_rate": FMT_FX,
                "rate": FMT_RATE, "days": FMT_DAYS, "quantity": "#,##0.00"}
HASH_ROWS = 10                  # sql_shell prints a result's hash at ten rows or more
# A quoted literal that opens like a ledger id (check_workbook.py ID_TOKEN's prefixes). A
# statement builds ids by concatenation ('F.m5.' || period); shown whole, the fragment
# reads as an id that resolves nowhere, so it is shown as an equal split literal.
ID_LITERAL = re.compile(r"'((?:RI|[EFPTSXCDQ])\.)([^']*)'")
# A LIKE pattern on a number ('%1350%') is shown as the equal concatenation, so it never
# reads as a percentage.
LIKE_NUMBER = re.compile(r"'(%?)(\d+)%'")
# An id written with a wildcard ('E.x.fs.pretax.*') in a constant's basis is shown as the
# ids it names, so every id on the tab resolves.
WILDCARD = re.compile(r"\b((?:RI|[EFPTSXCDQ])\.[A-Za-z0-9_.-]*[A-Za-z0-9])\.\*")


def _sql_text(text_: str, known: set[str]) -> str:
    t = LIKE_NUMBER.sub(lambda m: ("'%' || " if m.group(1) else "") + f"'{m.group(2)}' || '%'",
                        str(text_))
    return ID_LITERAL.sub(lambda m: m.group(0) if m.group(1) + m.group(2) in known
                          else f"'{m.group(1)}' || '{m.group(2)}'", t)


def _ids_named(text_: str, known: set[str]) -> str:
    return WILDCARD.sub(lambda m: ", ".join(sorted(k for k in known if k.startswith(m.group(1) + ".")))
                        or m.group(0), str(text_))


def _ledger(run_dir: pathlib.Path, kind: str, order: list[str]) -> dict[str, tuple[str, dict]]:
    """{id: (check, entry)} from every `<kind>-*.yaml`, checks in run order, first wins."""
    import resolve_roots
    out: dict[str, tuple[str, dict]] = {}
    refusals: list[str] = []
    files = sorted((run_dir / "workpapers").glob(f"{kind}-*.yaml"),
                   key=lambda f: (order.index(f.stem.split("-", 1)[1])
                                  if f.stem.split("-", 1)[1] in order else len(order), f.name))
    for f in files:
        for e in resolve_roots.ledger_entries(f, kind, refusals):
            out.setdefault(e["id"], (f.stem.split("-", 1)[1], e))
    if refusals:
        raise ValueError(f"{len(refusals)} ledger record(s) refused, the owning check's to "
                         f"rewrite: {refusals[:5]}")
    return out


def _value_cell(cell, e: dict) -> None:
    v, unit = e.get("value"), e.get("unit")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        cell.value, cell.style = v, S["Body"]
        cell.number_format = VALUE_FORMAT.get(unit, FMT_CENTS)
    elif "total_n" in e:
        text(cell, f"{e.get('included_n'):,} of {e.get('total_n'):,}")
    else:
        text(cell, "nil: " + str(e.get("zero_reason") or e.get("zero_basis")
                                 or "no value recorded").replace("_", " "))


def _expected(e: dict) -> str:
    v, unit = e.get("value"), e.get("unit")
    if "total_n" in e:
        return f"{e.get('included_n'):,} of {e.get('total_n'):,}"
    if isinstance(v, (int, float)) and not isinstance(v, bool) and unit:
        if _figures.is_money(unit):
            return _figures.fmt(v, unit, "cell")
        return _figures.fmt(v, unit) if unit == "count" else f"{v} {unit.replace('_', ' ')}"
    return "the value in this row"


def _input_id(i) -> str:
    return i if isinstance(i, str) else \
        (i.get("citation_id") or i.get("figure_id") or i.get("field") or "")


def _reads(e: dict) -> list[str]:
    """What the entry's statement reads directly, one per cell."""
    sql = e.get("sql")
    if isinstance(sql, dict):
        r = sql.get("reads") or {}
        return [*r.get("tables", []), *r.get("checks", []), *r.get("figures", []),
                *r.get("constants", [])]
    return [x for x in (_input_id(i) for i in e.get("inputs") or e.get("citations") or []) if x]


def _evidence_read(eid: str, evs: dict) -> str:
    hit = evs.get(eid)
    if not hit:
        return eid
    chk, e = hit
    if e.get("file_role") == "run_artifact":
        return f"derived from {(e.get('from_check') or chk).replace('_', ' ')}: {e.get('file')}"
    parts = [str(e.get("file") or "")]
    for key, word in (("sheet", "sheet"), ("cell", "cell"), ("rows", "rows")):
        if e.get(key):
            parts.append(f"{word} {e[key]}")
    if e.get("filter"):
        parts.append(f"filter {e['filter']}")
    ct = e.get("control_total")
    if isinstance(ct, dict) and ct.get("value") is not None:
        parts.append(f"control total {ct.get('column')} = {ct.get('value')}")
    return " · ".join(parts)


def _to_reperform(e: dict, roots: list[str], evs: dict, known: set[str]) -> str:
    if isinstance(e.get("sql"), dict):
        return (f"Run the expression over the tables in reads (Tables tab); the row where "
                f"id = '{e['id']}' gives {_expected(e)}.")
    parts = []
    if roots:
        parts.append("Read: " + "; ".join(_evidence_read(x, evs) for x in roots[:3])
                     + (f"; and {len(roots) - 3} more under root source" if len(roots) > 3 else ""))
    figs = [i for i in _reads(e) if i.startswith(("F.", "P."))]
    if figs:
        parts.append("Combine: " + ", ".join(figs[:8])
                     + (f" and {len(figs) - 8} more under reads" if len(figs) > 8 else ""))
    if e.get("expression"):
        parts.append("Arithmetic: " + _sql_text(e["expression"], known))
    if "total_n" in e:
        ex = "; ".join(f"{x.get('reason') or x.get('what') or x.get('name')}: "
                       f"{x.get('n') or x.get('count')}" for x in e.get("exclusions") or [])
        parts.append(f"Count the members: {e.get('included_n'):,} included of "
                     f"{e.get('total_n'):,}" + (f"; excluded: {ex}" if ex else ""))
    parts.append(f"Expected: {_expected(e)}")
    return " · ".join(parts)


def _spread(ws, row: int, first_col: int, ids: list[str]) -> None:
    for j, i in enumerate(ids):
        ident(ws.cell(row=row, column=first_col + j), i)


def _widths(ws, widths: dict[int, float]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def _check_tabs(run: dict, sheetnames: list[str]) -> dict[str, str]:
    """{check id: its own tab's name}."""
    from check_workbook import tab_owners
    owner, _ = tab_owners(run.get("checks") or [], sheetnames)
    out: dict[str, str] = {}
    for tab in sheetnames:
        if owner.get(tab):
            out.setdefault(owner[tab], tab)
    return out


def _sources(ws, subtitle, figs, evs, roots, tabs, known) -> None:
    max_reads = max([len(_reads(e)) for _, e in figs.values()] + [1])
    max_roots = max([len(roots.get(i) or []) for i in figs] + [1])
    labels = (["id", "label", "value", "unit", "disposition", "expression", "reads"]
              + [f"reads {i}" for i in range(2, max_reads + 1)]
              + ["root source"] + [f"root source {i}" for i in range(2, max_roots + 1)]
              + ["To reperform", "population", "caveats and carry-forwards", "from check"])
    band(ws, "Sources · Every figure, the statement that computed it and what it reads",
         f"{subtitle} · {len(figs):,} figures and populations")
    for i, label in enumerate(labels, start=2):
        ws.cell(row=4, column=i, value=label).style = S["Header"]
    c_reads, c_roots = 8, 8 + max_reads
    c_rep = c_roots + max_roots
    r = 4
    for fid, (chk, e) in figs.items():
        r += 1
        ident(ws.cell(r, 2), fid)
        text(ws.cell(r, 3), str(e.get("label", "")))
        _value_cell(ws.cell(r, 4), e)
        unit = e.get("unit") or ("population" if "total_n" in e else "")
        for col, v in ((5, unit), (6, e.get("disposition") or ""),
                       (7, _sql_text(e.get("expression") or "", known))):
            if v:
                text(ws.cell(r, col), v)
        _spread(ws, r, c_reads, _reads(e))
        _spread(ws, r, c_roots, roots.get(fid) or [])
        text(ws.cell(r, c_rep), _to_reperform(e, roots.get(fid) or [], evs, known))
        pop = e.get("population")
        if isinstance(pop, dict) and pop.get("total_n") is not None:
            text(ws.cell(r, c_rep + 1), f"{pop.get('included_n'):,} of {pop.get('total_n'):,}")
        elif isinstance(pop, dict) and isinstance(pop.get("ref"), str):
            ident(ws.cell(r, c_rep + 1), pop["ref"])
        elif isinstance(pop, str):
            ident(ws.cell(r, c_rep + 1), pop)
        if e.get("caveats"):
            text(ws.cell(r, c_rep + 2), "; ".join(str(x) for x in e["caveats"]))
        text(ws.cell(r, c_rep + 3), tabs.get(chk, chk.replace("_", " ")))
    _widths(ws, {2: 44, 3: 42, 4: 16, 5: 9, 6: 12, 7: 60, c_rep: 60, c_rep + 1: 16,
                 c_rep + 2: 48, c_rep + 3: 30})
    _widths(ws, {c: 34 for c in range(c_reads, c_rep)})
    for row in ws.iter_rows(min_row=5, min_col=7, max_col=7):
        for c in row:
            c.alignment = WRAP
    finish(ws, r, ledger=True)


def _totals(con, name: str, columns: list[tuple[str, str]]) -> str:
    money = [c for c, t in columns if t.upper().startswith(("DECIMAL", "DOUBLE"))]
    if not money:
        return ""
    import sql
    got = con.execute("SELECT " + ", ".join(f"sum({sql._ident(c)})" for c in money)
                      + f" FROM {sql._qualified(name)}").fetchone()
    return " · ".join(f"{c} {float(v):,.2f}" for c, v in zip(money, got) if v is not None)


def _result_hash(con, name: str) -> str | None:
    import sql
    import sql_shell
    cur = con.execute(f"SELECT * FROM {sql._qualified(name)}")
    description, rows = cur.description, cur.fetchall()
    if len(rows) < HASH_ROWS:
        return None
    foot = sql_shell.Shell().render(description, rows).strip().splitlines()[-1]
    m = re.search(r"hash ([0-9a-f]{16})", foot)
    return m.group(1) if m else None


def _tables(ws, subtitle, run_dir, evs, tabs, order, known) -> int:
    import sql
    d = sql.db(run_dir)
    d.refresh()
    con = d.con
    cols = ("table_name", "kind", "check_id", "description", "grain", "row_count", "file",
            "sheet", "header_at", "rows_read", "control_column", "control_total", "definition")
    rows = [dict(zip(cols, x)) for x in con.execute(
        f"SELECT {', '.join(cols)} FROM countz.tables").fetchall()]
    rank = {c: i for i, c in enumerate(order)}
    rows.sort(key=lambda t: (-1 if t["kind"] == "source" else rank.get(t["check_id"], len(rank)),
                             t["table_name"]))
    reads: dict[str, list[str]] = {}
    for reader, read in con.execute("SELECT reader, read FROM countz.reads ORDER BY 1, 2").fetchall():
        reads.setdefault(reader, []).append(read.removeprefix("const:"))
    evidence_of: dict[str, str] = {}
    for eid, (_, e) in evs.items():
        if e.get("cache_id"):
            evidence_of.setdefault(f"room.{e['cache_id']}", eid)
    max_reads = max([len(reads.get(t["table_name"], [])) for t in rows] + [1])
    labels = (["table", "what one row is", "made by", "rows", "totals", "result hash",
               "SQL or read", "evidence", "reads"] + [f"reads {i}" for i in range(2, max_reads + 1)])
    band(ws, "Tables · Every table the figures read: what one row is, how it was made, "
             "and what it reads",
         f"{subtitle} · {len(rows):,} tables")
    for i, label in enumerate(labels, start=2):
        ws.cell(row=4, column=i, value=label).style = S["Header"]
    r = 4
    for t in rows:
        r += 1
        name = t["table_name"]
        types = con.execute(f"DESCRIBE {sql._qualified(name)}").fetchall()
        source = t["kind"] == "source"
        ident(ws.cell(r, 2), name)
        about = t["description"]
        if source and t["grain"]:                       # "one order (contract)"
            about = f"{t['grain'][:1].upper()}{t['grain'][1:]} · {t['description']}"
        if about:
            text(ws.cell(r, 3), about)
        text(ws.cell(r, 4), "read from the data room" if source
             else tabs.get(t["check_id"], (t["check_id"] or "").replace("_", " ")))
        n = ws.cell(r, 5, t["row_count"])
        n.style, n.number_format = S["Body"], FMT_COUNT
        if totals := _totals(con, name, [(c[0], c[1]) for c in types]):
            text(ws.cell(r, 6), totals)
        if h := _result_hash(con, name):
            text(ws.cell(r, 7), h)
        if source:
            read = " · ".join(x for x in (
                t["file"], t["sheet"] and f"sheet {t['sheet']}",
                t["header_at"] and f"header {t['header_at']}",
                t["rows_read"] and f"rows {t['rows_read']}",
                t["control_column"] and f"control total {t['control_column']} "
                                        f"{t['control_total']:,.2f}") if x)
            text(ws.cell(r, 8), read)
            if evidence_of.get(name):
                ident(ws.cell(r, 9), evidence_of[name])
        elif t["definition"]:
            text(ws.cell(r, 8), _sql_text(t["definition"], known))
        _spread(ws, r, 10, reads.get(name, []))
    last = r
    _widths(ws, {2: 40, 3: 48, 4: 30, 5: 10, 6: 48, 7: 18, 8: 70, 9: 40})
    _widths(ws, {c: 36 for c in range(10, 10 + max_reads)})
    for row in ws.iter_rows(min_row=5, max_row=last, min_col=8, max_col=8):
        for c in row:
            c.alignment = WRAP

    consts = sql.constant_rows(run_dir)
    if consts:
        names = [c for c, _ in sql.CONSTANTS_COLUMNS]
        r = section(ws, next_block(last), "Constants")
        header(ws, r, ["name", "value", "unit", "kind", "where", "quote or basis",
                       "constant evidence"],
               ["id", "description", "count", "status", "description", "note", "id"])
        for x in consts:
            c = dict(zip(names, x))
            r += 1
            ident(ws.cell(r, 2), c["name"])
            text(ws.cell(r, 3), c["value"])
            for col, v in ((4, c["unit"]), (5, c["kind"]),
                           (6, ", ".join(str(v) for v in (c["file"], c["locator"]) if v)),
                           (7, _ids_named(c["quote"] or c["basis"] or "", known))):
                if v:
                    text(ws.cell(r, col), v)
            if c["citation_id"]:
                ident(ws.cell(r, 8), c["citation_id"])
    finish(ws, last, ledger=True)
    return len(rows)


def _evidence(ws, subtitle, evs, order, run: dict) -> None:
    labels = ["id", "kind", "file", "source", "role", "sheet", "anchor", "rows", "columns",
              "filter", "row count", "control total", "value", "value basis", "read date",
              "note, quote or label"]
    band(ws, "Evidence · Every read against the data room and against the checks' own tables",
         f"{subtitle} · {len(evs):,} reads")
    for i, label in enumerate(labels, start=2):
        ws.cell(row=4, column=i, value=label).style = S["Header"]
    r = 4
    for eid, (chk, e) in evs.items():
        r += 1
        role = str(e.get("file_role") or "").replace("_", " ")
        if e.get("file_role") == "run_artifact":
            role = f"derived — from {(e.get('from_check') or chk).replace('_', ' ')}"
        columns = "; ".join(f"{c.get('at')} {c.get('name')} ({c.get('holds')})"
                            for c in e.get("columns") or [])
        ct = e.get("control_total")
        if isinstance(ct, dict):
            v = ct.get("value")
            ct = f"{ct.get('column')} " + (f"{v:,.2f}" if isinstance(v, (int, float))
                                           and not isinstance(v, bool) else str(v))
        else:
            ct = ""
        value = e.get("value") if isinstance(e.get("value"), (int, float)) \
            and not isinstance(e.get("value"), bool) else None
        vals = [e.get("kind"), e.get("file"), e.get("source"), role, e.get("sheet"),
                e.get("header_at") or e.get("cell") or e.get("locator"), e.get("rows"), columns,
                e.get("filter"), e.get("row_count"), ct, value,
                str(e.get("value_source") or e.get("cell_kind") or "").replace("_", " "),
                str(e.get("read_at") or ""), e.get("note") or e.get("quote") or e.get("label_from")]
        ident(ws.cell(r, 2), eid)
        for col, v in enumerate(vals, start=3):
            if v is None or v == "":
                continue
            cell = ws.cell(r, col)
            if col == 14:
                cell.value, cell.style, cell.number_format = v, S["Body"], FMT_CENTS
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.value, cell.style, cell.number_format = v, S["Body"], FMT_COUNT
            else:
                text(cell, json.dumps(v) if isinstance(v, (dict, list)) else str(v))
    last = r
    r += 3
    ws.cell(row=r, column=2, value="Source roots").style = S["Section"]
    for s in run.get("sources") or []:
        r += 1
        text(ws.cell(r, 2), f"{s.get('id')}: {s.get('path')}")
    _widths(ws, {2: 44, 3: 10, 4: 48, 5: 12, 6: 26, 7: 10, 8: 12, 9: 12, 10: 60, 11: 36,
                 12: 12, 13: 30, 14: 16, 15: 16, 16: 12, 17: 60})
    finish(ws, last, ledger=True)


def write(wb, run_dir, subtitle: str) -> dict:
    """Append Sources, Tables and Evidence to `wb` (module docstring). Returns the row
    counts: {sources, tables, evidence}."""
    import resolve_roots
    run_dir = pathlib.Path(run_dir).resolve()
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    order = [c["id"] for c in run.get("checks") or []]
    fs = _figures.load(run_dir)
    if fs.conflicts:
        raise ValueError(f"the figure ledgers disagree on {len(fs.conflicts)} id(s), the "
                         f"owning checks' to settle: {sorted(fs.conflicts)[:5]}")
    collapsed = resolve_roots.collapse(run_dir)
    if collapsed["refusals"]:
        raise ValueError(f"resolve_roots.py refuses {len(collapsed['refusals'])} ledger "
                         f"record(s), the owning check's to rewrite: {collapsed['refusals'][:5]}")
    roots = {i: list(x.get("roots") or []) or list(x.get("via_check_output") or [])
             for i, x in collapsed["figures"].items()}
    figs = _ledger(run_dir, "figures", order)
    evs = _ledger(run_dir, "evidence", order)
    known = set(figs) | set(evs)
    for name in (SOURCES, TABLES, EVIDENCE):
        if name in wb.sheetnames:
            del wb[name]
    bind_styles(wb)
    tabs = _check_tabs(run, wb.sheetnames)
    _sources(wb.create_sheet(SOURCES), subtitle, figs, evs, roots, tabs, known)
    n_tables = _tables(wb.create_sheet(TABLES), subtitle, run_dir, evs, tabs, order, known)
    _evidence(wb.create_sheet(EVIDENCE), subtitle, evs, order, run)
    return {"sources": len(figs), "tables": n_tables, "evidence": len(evs)}
