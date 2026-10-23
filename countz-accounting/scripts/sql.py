#!/usr/bin/env python3
"""The run's tables in SQL (DuckDB). A parse writes a table; everything computed from it is
SQL, and the SQL is its lineage.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from sql import run_sql
    from figures import Ledger

    run_sql(\"\"\"CREATE OR REPLACE TABLE r5_position.open_items AS
               SELECT customer_id, due_date, open_amount FROM room.aging_2025_06_30
               WHERE open_amount <> 0;
               COMMENT ON TABLE r5_position.open_items IS
                 'One row per open invoice at 30 June 2025: its due date and amount open.'\"\"\")
    df = run_sql("SELECT count(*) AS n FROM r5_position.open_items")   # a polars DataFrame
    L = Ledger(RUN, "r5_position")
    L.figures('''SELECT 'F.r5.past_due.2025-06' AS id, 'Past due at 30 June 2025' AS label,
                        'usd' AS unit, sum(open_amount) AS value
                 FROM r5_position.open_items WHERE due_date < DATE '2025-06-30' ''')
    L.write()

**The tables.** `room.<id>` is a table parsed from a data-room file (scripts/cache.py).
`<check>.<name>` is a check's table: one `CREATE [OR REPLACE] TABLE <check>.<name> AS
SELECT ...` made it (stored at `tables/<check>/<name>.parquet` with its statement), or
`items.write_items` wrote it (`checks/<check>-<name>.parquet`). The catalog describes them:
`countz.tables` (what each table is; for a parsed one its file, sheet, rows and control
total; for a check's table the statement that made it), `countz.columns` (each column's
type, description, unit, location in the file and parse), `countz.figures` (every figure
minted), `countz.ties` (every tie: its sides, difference and status), `countz.reads` (what
each statement reads) and `countz.functions` (the macros).
`fig('F.x')` is a figure's value. `SELECT * FROM lineage('F.x')` lists the statements
behind a figure or table in the order a re-performer runs them, down to the parsed tables
and the file, sheet and rows each was read from.

A statement reads these by name: no file function, and of table functions only `range`,
`generate_series` and `unnest`. `COMMENT ON TABLE <check>.<name> IS 'One row per ...'`
says what one row of a check's table is, and run_sql refuses a CREATE that leaves its
table without one: follow the CREATE with its COMMENT in the same call. `COMMENT ON
COLUMN <check>.<name>.<column> IS '...'` describes a column. Both are kept across a
CREATE OR REPLACE. The workbook's Tables tab shows the description beside the statement. A check writes only its own schema; `room` and `countz`
are read only. Aliases are lower case, because an upper-case `P.x` reads as a ledger id.

**Constants are rows of `room.constants`** (`name`, `value`, `unit`, `kind`, and where it
comes from). `stated`: a document says it (`file`, `locator`, `quote`). `declared`: a
parameter of the plan, one row per numeric or date `params` key (`plan/<recipe>.json`).
`chosen`: the step's own parameter, with its `basis`. `Ledger.constants(rows)` writes a
check's stated and chosen rows; `const('name')` reads a number, `const_date('name')` a
date and `const_text('name')` a text. A statement that makes a table, a figure, a
population or an item table types no other value:
- a number only as a whole number from 0 to 12, 365 or 366, or a year (1900 to 2100);
- a date only as a declared date, or the first day of the fiscal year it ends;
- no record id compared to a column (`contract_id = 'SO-01375'`): select the row by what
  makes it that row, or state the id as a constant;
- no typed `result` or `status`: compute it (`CASE WHEN ... THEN 'held' ...`), and put a
  judgment in `ruling`, `verdict` or `disposition` with its basis.

**Figures and populations are rows.** `Ledger.figures(query)` mints one figure per row:
columns `id`, `label`, `unit`, `value`, and optionally `population`, `zero_basis`,
`disposition`, `caveats` (a list). `Ledger.populations(query)` mints one `P.` entry per
row: `id`, `label`, `total_n`, `included_n`, and `exclusions` (a list of
`{what, n}` structs) where `included_n < total_n`. Every row is minted or none is. The
statement is each entry's `expression`; the tables and figures it reads, traced through
the check tables to the parsed ones, are its `inputs`.

**Exploring.** `scripts/countz-sql -agent -init <run>/catalog.sql -c "<sql>"` runs any SQL
over the same catalog and records nothing. Every table write rewrites `catalog.sql`.

`verify(run_dir, check=None)` re-runs every statement and fails:
- a figure or population whose value changed (money beyond half its minor unit, a count
  by any amount, anything else beyond 1e-9);
- a check table whose rows its statement no longer returns, or that no statement made
  (an item table written from rows);
- a figure or population computed outside SQL. A ledger entry may be minted outside SQL
  only when it is a tie's difference, a figure with no value, or a passthrough of stated
  cells (`as_stated`, every input a `cell` citation); a value a passage or the plan states
  is a constant;
- a statement that no longer runs;
- a data-room span with no `cache_id`;
- a stated constant whose file changed or no longer holds its quote.

    sql.py verify <run_dir> [--check <check>]        exit 1 on a failure
    sql.py catalog <run_dir>                         rewrite <run_dir>/catalog.sql

Run with `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cache  # noqa: E402  sibling: the parsed tables and their metadata
import style  # noqa: E402  sibling: a currency's minor units

TABLE_SCHEMA = "countz-accounting/table@1"
TABLES_DIR = "tables"
CATALOG = "catalog.sql"
RESERVED = frozenset({"room", "countz", "main", "temp", "system", "information_schema",
                      "pg_catalog"})
CHECK = re.compile(r"[a-z0-9][a-z0-9_]{0,30}")          # check_playbook.CHECK_ID
NAME = re.compile(r"[a-z0-9][a-z0-9_]*")
ITEM_TABLE = re.compile(r"(?P<check>[a-z0-9][a-z0-9_]*)-(?P<table>[a-z0-9][a-z0-9_-]*)")
TABLE_FUNCTIONS = frozenset({"range", "generate_series", "unnest"})
_IDENT = r'(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_]*)'
CREATE = re.compile(rf"\s*CREATE\s+(?P<replace>OR\s+REPLACE\s+)?TABLE\s+(?P<schema>{_IDENT})"
                    rf"\s*\.\s*(?P<name>{_IDENT})\s+AS\s+(?P<body>.+?)\s*;?\s*\Z", re.I | re.S)
COMMENT = re.compile(rf"\s*COMMENT\s+ON\s+(?P<what>TABLE|COLUMN)\s+(?P<schema>{_IDENT})\s*\.\s*"
                     rf"(?P<name>{_IDENT})(?:\s*\.\s*(?P<col>{_IDENT}))?\s+IS\s+"
                     rf"'(?P<text>(?:[^']|'')*)'\s*;?\s*\Z", re.I | re.S)
# An identifier that reads as a ledger id (EVIDENCE.md § 0) once string literals are blanked.
ID_LIKE = re.compile(r"(?<![\w.\"])[A-Z]{1,2}\.[A-Za-z0-9_]")
QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")

CONSTANTS_DIR = "constants"
CONSTANTS_SCHEMA = "countz-accounting/constants@1"
CONSTANT_NAME = re.compile(r"[a-z][a-z0-9_]{0,59}")
CONSTANT_UNITS = tuple(style.CURRENCIES) + style.OTHER_UNITS + ("date", "text")
CONSTANTS_COLUMNS = (("name", "VARCHAR"), ("value", "VARCHAR"), ("unit", "VARCHAR"),
                     ("kind", "VARCHAR"), ("file", "VARCHAR"), ("source", "VARCHAR"),
                     ("locator", "VARCHAR"), ("quote", "VARCHAR"), ("basis", "VARCHAR"),
                     ("check_id", "VARCHAR"), ("citation_id", "VARCHAR"),
                     ("sha256", "VARCHAR"))
CONST_FUNCS = {"const": "number", "const_date": "date", "const_text": "text"}
DATE_TYPES = frozenset({"DATE", "TIMESTAMP", "TIMESTAMPTZ", "TIMESTAMP WITH TIME ZONE",
                        "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP_NS"})
NUMBER_TYPES = frozenset({"DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL", "INTEGER", "INT",
                          "BIGINT", "SMALLINT", "TINYINT", "HUGEINT", "UBIGINT", "UINTEGER"})
ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T][0-9:.+-]*)?")
# A record's own id (`SO-01375`, `GJ25-000097`, `JE-YE-25-044`): letters and digits joined
# by hyphens. A period key (`2025-12`, `ltm_2026-07`) and a code (`new_12m`) are not one.
RECORD_ID = re.compile(r"(?=[^0-9]*[0-9])(?=[^A-Za-z]*[A-Za-z])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+")
TYPED_COLUMNS = ("result", "status")

# The kit's macros: (name, signature, what it returns, definition).
FUNCTIONS = (
    ("fig", "fig(id)", "the value of figure `id` (countz.figures)",
     "CREATE MACRO fig(i) AS (SELECT first(value) FROM countz.figures WHERE id = i)"),
    ("cell", "cell(id)", "figure `id` as a table cell of the check's page (scripts/render.py)",
     "CREATE MACRO cell(i) AS {'id': i, 'value': (SELECT first(value) FROM countz.figures "
     "WHERE id = i)}"),
    ("tie", "tie(id)", "tie `id`: `label`, its figures `a`, `b` and `difference`, and its "
     "`status` (countz.ties)",
     "CREATE MACRO tie(t) AS (SELECT {'label': label, 'a': side_a, 'b': side_b, "
     "'difference': difference_figure, 'status': status} FROM countz.ties WHERE id = t)"),
    ("const", "const(name)", "the number constant `name` (room.constants)",
     "CREATE MACRO const(n) AS (SELECT CAST(value AS DECIMAL(18, 6)) FROM room.constants "
     "WHERE name = n)"),
    ("const_date", "const_date(name)", "the date constant `name` (room.constants)",
     "CREATE MACRO const_date(n) AS (SELECT CAST(value AS DATE) FROM room.constants "
     "WHERE name = n)"),
    ("const_text", "const_text(name)", "the text constant `name` (room.constants)",
     "CREATE MACRO const_text(n) AS (SELECT value FROM room.constants WHERE name = n)"),
    ("months_elapsed", "months_elapsed(start, at)",
     "the months of a straight-line schedule elapsed at `at`, the start month and the month "
     "of `at` both counted; 0 before the start",
     "CREATE MACRO months_elapsed(start_d, at_d) AS "
     "greatest(0, datediff('month', start_d, at_d) + 1)"),
    ("carrying_amount", "carrying_amount(amount, start, months, at)",
     "what remains at `at` of `amount` amortized straight-line over `months` from the start "
     "month (the start month counted), the amortization to date rounded to the cent",
     "CREATE MACRO carrying_amount(amount, start_d, months, at_d) AS "
     "round(amount - round(amount * least(months, months_elapsed(start_d, at_d)) / months, 2), 2)"),
)
TABLES_COLUMNS = (("table_name", "VARCHAR"), ("kind", "VARCHAR"), ("check_id", "VARCHAR"),
                  ("description", "VARCHAR"), ("grain", "VARCHAR"), ("row_count", "BIGINT"),
                  ("file", "VARCHAR"), ("source", "VARCHAR"), ("sheet", "VARCHAR"),
                  ("header_at", "VARCHAR"), ("rows_read", "VARCHAR"), ("sha256", "VARCHAR"),
                  ("control_column", "VARCHAR"), ("control_total", "DOUBLE"),
                  ("stated_total", "DOUBLE"), ("stated_where", "VARCHAR"),
                  ("stated_agrees", "BOOLEAN"), ("definition", "VARCHAR"),
                  ("written_at", "VARCHAR"))
COLUMNS_COLUMNS = (("table_name", "VARCHAR"), ("column_name", "VARCHAR"),
                   ("ordinal", "INTEGER"), ("type", "VARCHAR"), ("description", "VARCHAR"),
                   ("unit", "VARCHAR"), ("location", "VARCHAR"), ("parse", "VARCHAR"))
FIGURES_COLUMNS = (("id", "VARCHAR"), ("check_id", "VARCHAR"), ("label", "VARCHAR"),
                   ("value", "DOUBLE"), ("unit", "VARCHAR"), ("statement", "VARCHAR"))
TIES_COLUMNS = (("id", "VARCHAR"), ("check_id", "VARCHAR"), ("label", "VARCHAR"),
                ("unit", "VARCHAR"), ("side_a", "VARCHAR"), ("side_b", "VARCHAR"),
                ("difference_figure", "VARCHAR"), ("status", "VARCHAR"))
FUNCTIONS_COLUMNS = (("name", "VARCHAR"), ("signature", "VARCHAR"), ("returns", "VARCHAR"))
READS_COLUMNS = (("reader", "VARCHAR"), ("read", "VARCHAR"))
LINEAGE = """CREATE MACRO lineage(f) AS TABLE
WITH RECURSIVE walk(node, depth) AS (
    SELECT f, 0
    UNION
    SELECT r.read, w.depth + 1 FROM walk w JOIN countz.reads r ON r.reader = w.node
    WHERE w.depth < 64),
nodes AS (SELECT node, max(depth) AS depth FROM walk GROUP BY node)
SELECT row_number() OVER (ORDER BY n.depth DESC, n.node) AS step, n.node,
       coalesce(t.kind, CASE WHEN n.node LIKE 'F.%' THEN 'figure'
                             WHEN c.name IS NOT NULL THEN 'constant' END) AS kind,
       coalesce(t.definition, g.statement) AS statement,
       CASE WHEN g.id IS NOT NULL THEN 'id = ' || chr(39) || g.id || chr(39) END AS row_key,
       coalesce(CAST(g.value AS VARCHAR), c.value) AS value, coalesce(t.file, c.file) AS file,
       t.sheet, t.header_at, t.rows_read, t.control_column, t.control_total,
       c.unit, c.kind AS constant_kind, c.locator, c.quote, c.basis
FROM nodes n LEFT JOIN countz.tables t ON t.table_name = n.node
LEFT JOIN countz.figures g ON g.id = n.node
LEFT JOIN room.constants c ON n.node = 'const:' || c.name
ORDER BY step"""
LINEAGE_ABOUT = ("lineage", "SELECT * FROM lineage('F.x')",
                 "the statements behind a figure or table, in the order a re-performer runs "
                 "them, down to the parsed tables (file, sheet, rows) and the constants "
                 "(file, locator, quote) each was read from")


def _duckdb():
    try:
        import duckdb
    except ImportError as exc:                      # pragma: no cover
        sys.exit(f"sql.py needs duckdb ({exc}); run it as "
                 "`uv run --project ${CLAUDE_PLUGIN_ROOT} python3`")
    return duckdb


def engine() -> str:
    return f"duckdb {_duckdb().__version__}"


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _unquote(name: str) -> str:
    return name[1:-1].replace('""', '"') if name.startswith('"') else name.lower()


def _literal(s) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) and math.isfinite(v) else \
            (str(v) if isinstance(v, int) else "NULL")
    return _literal(v)


def _plain_number(text: str) -> bool:
    """A number a statement may type: a whole number from 0 to 12, 365 or 366, or a year."""
    try:
        d = decimal.Decimal(text)
    except decimal.InvalidOperation:
        return False
    if d != d.to_integral_value():
        return False
    return abs(d) <= 12 or abs(d) in (365, 366) or 1900 <= d <= 2100


def _float(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# -- the catalog ---------------------------------------------------------------------------
def table_metadata(path) -> dict | None:
    """The metadata a check table's parquet holds, or None for one written without it."""
    try:
        raw = cache._pl().read_parquet_metadata(pathlib.Path(path)).get(cache.META)
    except Exception:
        return None
    return json.loads(raw) if raw else None


_LEDGERS: dict[pathlib.Path, tuple] = {}


def _ledger(path: pathlib.Path) -> list:
    """A figures ledger's entries, parsed once per version of the file."""
    import yaml
    st = path.stat()
    key = (st.st_mtime_ns, st.st_size)
    if _LEDGERS.get(path, (None,))[0] != key:
        doc = yaml.load(path.read_text(encoding="utf-8"),
                        Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) or []
        if not isinstance(doc, list):
            raise ValueError(f"{path}: the ledger is not a YAML list (EVIDENCE.md § 0)")
        _LEDGERS[path] = (key, doc)
    return _LEDGERS[path][1]


def _reads(reader: str, reads: dict | None) -> list[tuple[str, str]]:
    r = reads or {}
    return [(reader, x) for k in ("tables", "checks", "figures") for x in r.get(k) or []] + \
        [(reader, f"const:{c}") for c in r.get("constants") or []]


def _ledger_reads(run_dir: pathlib.Path) -> list[tuple[str, str]]:
    """(figure or population id, what its statement reads) for every SQL entry."""
    out = []
    for f in sorted((run_dir / "workpapers").glob("figures-*.yaml")):
        for e in _ledger(f):
            if isinstance(e, dict) and isinstance(e.get("sql"), dict):
                out += _reads(str(e.get("id")), e["sql"].get("reads"))
    return out


def _ledger_figures(run_dir: pathlib.Path) -> list[tuple]:
    """(id, check, label, value, unit, statement) for every figure in the run's ledgers."""
    out = []
    for f in sorted((run_dir / "workpapers").glob("figures-*.yaml")):
        check = f.stem.removeprefix("figures-")
        for e in _ledger(f):
            if isinstance(e, dict) and str(e.get("id", "")).startswith("F."):
                st = (e.get("sql") or {}).get("text") if isinstance(e.get("sql"), dict) else None
                out.append((e["id"], check, str(e.get("label") or ""), _float(e.get("value")),
                            str(e.get("unit") or ""), st))
    return out


def _ledger_ties(run_dir: pathlib.Path) -> list[tuple]:
    """(id, check, label, unit, side_a, side_b, difference_figure, status) for every tie,
    from the record each tie keeps on its difference figure."""
    out = []
    for f in sorted((run_dir / "workpapers").glob("figures-*.yaml")):
        check = f.stem.removeprefix("figures-")
        for e in _ledger(f):
            t = e.get("tie") if isinstance(e, dict) else None
            if isinstance(t, dict) and t.get("id"):
                out.append((t["id"], check, str(t.get("label") or ""), str(t.get("unit") or ""),
                            (t.get("side_a") or {}).get("figure_id"),
                            (t.get("side_b") or {}).get("figure_id"),
                            t.get("difference_figure"), t.get("status")))
    return out


def _canon(v, unit: str) -> str:
    """A constant's value as stored: a number in plain digits, a date as YYYY-MM-DD."""
    if unit == "text":
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"a text constant is a non-empty string, not {v!r}")
        return v
    if unit == "date":
        if isinstance(v, datetime.datetime):
            v = v.date()
        if isinstance(v, datetime.date):
            return v.isoformat()
        if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return datetime.date.fromisoformat(v).isoformat()
        raise ValueError(f"a date constant is a date or YYYY-MM-DD, not {v!r}")
    if isinstance(v, bool) or not isinstance(v, (int, float, decimal.Decimal)):
        raise ValueError(f"a {unit} constant is a number, not {v!r}")
    d = v if isinstance(v, decimal.Decimal) else decimal.Decimal(str(v))
    if not d.is_finite():
        raise ValueError(f"a {unit} constant is a finite number, not {v!r}")
    d = d.normalize()
    if -d.as_tuple().exponent > 6:
        raise ValueError(f"{v!r}: a constant has at most 6 decimals")
    return format(d, "f")


def _playbook(run_dir: pathlib.Path) -> pathlib.Path | None:
    try:
        plan = json.loads((run_dir / "run.json").read_text(encoding="utf-8")).get("plan") or {}
    except (OSError, ValueError):
        return None
    p = run_dir / plan["playbook"] if plan.get("playbook") else None
    return p if p is not None and p.is_file() else None


def _declared(run_dir: pathlib.Path) -> list[tuple]:
    """One `declared` constant per number or date in the plan's step params: `name` the
    key, or `<key>__<step>` where the steps disagree on it."""
    path = _playbook(run_dir)
    if path is None:
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rel = path.relative_to(run_dir).as_posix()
    found: dict[str, dict[str, list[str]]] = {}
    units: dict[tuple[str, str], str | None] = {}
    basis: dict[str, str] = {}
    for s in doc.get("steps") or []:
        params = s.get("params") or {}
        for k, v in params.items():
            if not CONSTANT_NAME.fullmatch(k) or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                unit = None
            elif isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                unit = "date"
            else:
                continue
            try:
                text = _canon(v, unit or "number")
            except ValueError:
                continue
            found.setdefault(k, {}).setdefault(text, []).append(str(s.get("id")))
            units[(k, text)] = unit
            for b in (f"{k}_basis", f"{k}_declared"):
                if isinstance(params.get(b), str) and k not in basis:
                    basis[k] = params[b]
    every = len(doc.get("steps") or [])
    out = []
    for k, values in sorted(found.items()):
        for text, steps in values.items():
            names = [k] if len(values) == 1 else [f"{k}__{s}" for s in steps]
            for name in names:
                where = steps if len(values) == 1 else [name.rsplit("__", 1)[1]]
                at = "every step" if len(where) == every else "step " + ", ".join(where)
                out.append((name, text, units[(k, text)], "declared", rel, None,
                            f"params.{k}, {at}", None, basis.get(k), None, None, None))
    return out


def _rows_sha256(rows: list) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def _stored_constants(run_dir: pathlib.Path) -> list[tuple]:
    out = []
    for p in sorted((run_dir / CONSTANTS_DIR).glob("*.json")):
        for r in json.loads(p.read_text(encoding="utf-8")).get("rows") or []:
            out.append(tuple(r.get(c) for c, _ in CONSTANTS_COLUMNS))
    return out


def constant_rows(run_dir) -> list[tuple]:
    """Every row of `room.constants`: the plan's declared ones, then each check's."""
    run_dir = pathlib.Path(run_dir).resolve()
    return _declared(run_dir) + _stored_constants(run_dir)


def tables(run_dir) -> list[dict]:
    """Every table the run holds: {name, kind, check, path, meta}, `name` as a query writes it."""
    run_dir = pathlib.Path(run_dir)
    out = []
    for e in cache.manifest(run_dir)["files"]:
        out.append({"name": f"room.{e['id']}", "kind": "source", "check": None,
                    "path": run_dir / e["parquet"], "meta": e})
    for p in sorted((run_dir / TABLES_DIR).glob("*/*.parquet")):
        if CHECK.fullmatch(p.parent.name) and NAME.fullmatch(p.stem):
            out.append({"name": f"{p.parent.name}.{p.stem}", "kind": "derived",
                        "check": p.parent.name, "path": p, "meta": table_metadata(p)})
    for p in sorted((run_dir / "checks").glob("*-*.parquet")):
        m = ITEM_TABLE.fullmatch(p.stem)
        if m:
            out.append({"name": f"{m.group('check')}.{m.group('table')}", "kind": "item",
                        "check": m.group("check"), "path": p, "meta": table_metadata(p)})
    return out


def _qualified(name: str) -> str:
    schema, _, t = name.partition(".")
    return f"{_ident(schema)}.{_ident(t)}"


def _insert(table: str, cols, rows) -> list[str]:
    out = [f"CREATE TABLE {table} (" + ", ".join(f"{c} {t}" for c, t in cols) + ");"]
    if rows:
        out.append(f"INSERT INTO {table} VALUES\n" + ",\n".join(
            "(" + ", ".join(_value(v) for v in r) + ")" for r in rows) + ";")
    return out


def catalog_statements(run_dir, figures: list[tuple] | None = None,
                       reads: list[tuple] | None = None) -> list[str]:
    """The statements that build the run's catalog in an empty database."""
    run_dir = pathlib.Path(run_dir).resolve()
    ts = tables(run_dir)
    schemas = sorted({"room", "countz"} | {t["check"] for t in ts if t["check"]})
    out = [f"CREATE SCHEMA {_ident(s)};" for s in schemas]
    trows, crows = [], []
    probe = _duckdb().connect(":memory:")
    for t in ts:
        read = f"read_parquet({_literal(t['path'])})"
        out.append(f"CREATE VIEW {_qualified(t['name'])} AS SELECT * FROM {read};")
        types = probe.execute(f"DESCRIBE SELECT * FROM {read}").fetchall()
        m = t["meta"] or {}
        if t["kind"] == "source":
            ct, st = m.get("control_total") or {}, m.get("stated") or {}
            trows.append((t["name"], "source", None, m.get("what"), m.get("grain"),
                          m.get("row_count"), m.get("file"), m.get("source"), m.get("sheet"),
                          m.get("header_at"), m.get("rows"), m.get("sha256"), ct.get("column"),
                          _float(ct.get("value")), _float(st.get("value")), st.get("where"),
                          st.get("agrees"), None, m.get("written_at")))
        else:
            trows.append((t["name"], t["kind"], t["check"], m.get("description"),
                          m.get("grain"), m.get("row_count"), None, None, None, None, None,
                          None, None, None, None, None, None, m.get("sql"), m.get("written_at")))
        about = {c.get("name"): c for c in m.get("columns") or []}
        for i, (name, typ, *_) in enumerate(types, 1):
            c = about.get(name, {})
            crows.append((t["name"], name, i, typ, c.get("description"), c.get("unit"),
                          c.get("at"), c.get("parse")))
    out += _insert("countz.tables", TABLES_COLUMNS, trows)
    out += _insert("countz.columns", COLUMNS_COLUMNS, crows)
    out += _insert("countz.figures", FIGURES_COLUMNS,
                   _ledger_figures(run_dir) if figures is None else figures)
    out += _insert("countz.ties", TIES_COLUMNS, _ledger_ties(run_dir))
    edges = [e for t in ts if t["kind"] != "source"
             for e in _reads(t["name"], (t["meta"] or {}).get("reads"))]
    edges += _ledger_reads(run_dir) if reads is None else reads
    out += _insert("countz.reads", READS_COLUMNS, sorted(set(edges)))
    out += _insert("room.constants", CONSTANTS_COLUMNS, constant_rows(run_dir))
    out += _insert("countz.functions", FUNCTIONS_COLUMNS,
                   [f[:3] for f in FUNCTIONS] + [LINEAGE_ABOUT])
    out += [f[3] + ";" for f in FUNCTIONS] + [LINEAGE + ";"]
    return out


@contextlib.contextmanager
def _locked(path: pathlib.Path):
    import fcntl                                   # POSIX only: macOS and Linux
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def write_catalog(run_dir) -> pathlib.Path:
    """Rewrite `<run_dir>/catalog.sql` from the tables and ledgers on disk."""
    run_dir = pathlib.Path(run_dir).resolve()
    out = run_dir / CATALOG
    with _locked(run_dir / ".catalog.lock"):
        text = ("-- The run's tables, their metadata and the kit's macros (scripts/sql.py).\n"
                "-- countz-sql -agent -init catalog.sql -c \"SELECT * FROM countz.tables\"\n"
                + "\n".join(catalog_statements(run_dir)) + "\n")
        cache._atomic(out, text)
    return out


# -- typed values --------------------------------------------------------------------------
def _year_start(iso: str) -> str:
    """The first day of the year that ends on `iso`."""
    d = datetime.date.fromisoformat(iso)
    try:
        before = d.replace(year=d.year - 1)
    except ValueError:                             # 29 February
        before = d.replace(year=d.year - 1, day=28)
    return (before + datetime.timedelta(days=1)).isoformat()


def _reads_rows(o) -> bool:
    """Whether an expression's value depends on a row, a figure or a constant."""
    if isinstance(o, dict):
        if o.get("class") in ("COLUMN_REF", "SUBQUERY", "STAR", "WINDOW", "COLUMN"):
            return True
        if o.get("class") == "FUNCTION" and (o.get("function_name") == "fig"
                                             or o.get("function_name") in CONST_FUNCS
                                             or not o.get("arguments")):
            return True
        return any(_reads_rows(v) for v in o.values())
    if isinstance(o, list):
        return any(_reads_rows(v) for v in o)
    return False


def _values_columns(node) -> list[list] | None:
    """The columns of a `VALUES` list a query node selects whole, else None."""
    if not isinstance(node, dict):
        return None
    if node.get("type") == "EXPRESSION_LIST":
        rows = node.get("values") or []
        return [list(c) for c in zip(*rows)] if rows else []
    if node.get("type") == "SELECT_NODE" and [e.get("class") for e in node.get("select_list") or []] \
            == ["STAR"]:
        return _values_columns(node.get("from_table"))
    if node.get("type") == "SUBQUERY":
        return _values_columns((node.get("subquery") or {}).get("node"))
    return None


def _typed(stmt, dates: set[str]) -> list[str]:
    """What a recorded statement types that a constant, a figure or a row should supply."""
    numbers, bad_dates, ids, typed = [], [], [], []

    def number(text):
        if not _plain_number(text):
            numbers.append(text)

    def string(text, compared):
        m = ISO_DATE.fullmatch(text)
        if m and compared and m.group(1) not in dates:
            bad_dates.append(text)
        elif compared and RECORD_ID.fullmatch(text):
            ids.append(text)

    def named(names, cols):
        for name, col in zip(names, cols):
            if str(name).lower() in TYPED_COLUMNS and not _reads_rows(col):
                typed.append(str(name))

    def walk(o, compared=False):
        if isinstance(o, list):
            for v in o:
                walk(v, compared)
            return
        if not isinstance(o, dict) or o.get("type") == "LIMIT_MODIFIER":
            return
        c = o.get("class")
        lit = o.get("literal") if c == "CONSTANT" else None
        if isinstance(lit, dict) and lit.get("text") is not None:
            if lit.get("kind") == "STRING":
                string(str(lit["text"]), compared)
            elif re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(lit["text"])):
                number(str(lit["text"]))
        if c == "CAST" and (o.get("child") or {}).get("class") == "CONSTANT":
            t = str((o.get("type_expr") or {}).get("type_name") or "").upper()
            text = str(((o["child"].get("literal")) or {}).get("text"))
            if t in DATE_TYPES:
                m = ISO_DATE.fullmatch(text)
                if not m or m.group(1) not in dates:
                    bad_dates.append(text)
                return
            if t in NUMBER_TYPES:
                number(text)
                return
            if t == "INTERVAL":
                for n in re.findall(r"\d+(?:\.\d+)?", text):
                    number(n)
                return
        if o.get("alias") and str(o["alias"]).lower() in TYPED_COLUMNS and c is not None \
                and not _reads_rows(o):
            typed.append(str(o["alias"]))
        if isinstance(o.get("cte_map"), dict):
            for kv in o["cte_map"].get("map") or []:
                v = kv.get("value") or {}
                cols = _values_columns(v.get("query_node"))
                if v.get("aliases") and cols is not None:
                    named(v["aliases"], cols)
        if o.get("column_name_alias"):
            cols = _values_columns(o)
            if cols is not None:
                named(o["column_name_alias"], cols)
        cmp = c in ("COMPARISON", "BETWEEN") or (c == "OPERATOR" and o.get("type") in
                                                  ("COMPARE_IN", "COMPARE_NOT_IN"))
        for k, v in o.items():
            walk(v, cmp)

    walk(stmt)
    out = []
    if numbers:
        out.append(f"number(s) {sorted(set(numbers))}: state a document's number, a plan "
                   f"parameter or the step's own choice as a constant and read it with "
                   f"const('name'), or read it from a table or fig()")
    if bad_dates:
        out.append(f"date(s) {sorted(set(bad_dates))}: a typed date is a declared date or "
                   f"the first day of its fiscal year; state any other as a constant and read "
                   f"it with const_date('name'), or compute it from one")
    if ids:
        out.append(f"record id(s) {sorted(set(ids))} compared to a column: select the rows by "
                   f"what makes them those rows (a class, a date, a document), or state the id "
                   f"from its document and read it with const_text('name')")
    if typed:
        out.append(f"column(s) {sorted(set(typed))} as typed values: compute a result or a "
                   f"status from the rows (CASE WHEN ... THEN 'held' ELSE 'departed' END); a "
                   f"judgment goes in `ruling`, `verdict` or `disposition` with its basis")
    return out


# -- the connection ------------------------------------------------------------------------
class Db:
    """One in-memory DuckDB connection over a run's catalog, rebuilt when a table changes."""

    def __init__(self, run_dir):
        self.run_dir = pathlib.Path(run_dir).resolve()
        self.held: dict[str, tuple] = {}         # figures minted this session, not yet written
        self.held_reads: dict[str, list] = {}    # and what their statements read
        self._ledgers: list = []
        self._stamp = None
        self._load()

    def _signature(self):
        files = [*(self.run_dir / cache.CACHE_DIR).glob("*.parquet"),
                 *(self.run_dir / TABLES_DIR).glob("*/*.parquet"),
                 *(self.run_dir / "checks").glob("*-*.parquet"),
                 *(self.run_dir / CONSTANTS_DIR).glob("*.json"),
                 *(self.run_dir / "workpapers").glob("figures-*.yaml"),
                 *filter(None, [_playbook(self.run_dir)])]
        return tuple(sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files))

    def _load(self) -> None:
        self.con = _duckdb().connect(":memory:")
        figs = {f[0]: f for f in _ledger_figures(self.run_dir)}
        figs.update(self.held)
        edges = [e for e in _ledger_reads(self.run_dir) if e[0] not in self.held_reads]
        edges += [e for v in self.held_reads.values() for e in v]
        for st in catalog_statements(self.run_dir, list(figs.values()), edges):
            self.con.execute(st)
        self.tables = {t["name"]: t for t in tables(self.run_dir)}
        self._stamp = self._signature()

    def refresh(self) -> None:
        for L in self._ledgers:                  # what an attached Ledger has minted
            for fid, e in L.entries.items():
                if fid.startswith("F."):
                    row = (fid, L.check, str(e.get("label") or ""), _float(e.get("value")),
                           str(e.get("unit") or ""), ((e.get("sql") or {}).get("text")))
                    if self.held.get(fid) != row:
                        self.hold(row)
        if self._signature() != self._stamp:
            self._load()

    def attach(self, L) -> None:
        if not any(x is L for x in self._ledgers):
            self._ledgers.append(L)

    def hold(self, row: tuple, reads: dict | None = None) -> None:
        """Make a figure just minted readable by `fig()`, and by `lineage()` with `reads`."""
        self.held[row[0]] = row
        self.con.execute("DELETE FROM countz.figures WHERE id = ?", [row[0]])
        self.con.execute("INSERT INTO countz.figures VALUES (?, ?, ?, ?, ?, ?)", list(row))
        if reads is not None:
            self.held_reads[row[0]] = _reads(row[0], reads)
            self.con.execute("DELETE FROM countz.reads WHERE reader = ?", [row[0]])
            for e in self.held_reads[row[0]]:
                self.con.execute("INSERT INTO countz.reads VALUES (?, ?)", list(e))

    # -- reading a statement -------------------------------------------------------------
    def lineage(self, query: str, recorded: bool = False) -> dict:
        """What one SELECT reads, from its parse tree, without running it: `tables` (room
        tables), `checks` (check tables), `figures` (`fig()` ids) and `constants`
        (`const*()` names), each in first-read order. Refuses a statement that is not one
        SELECT, a file or table function, a table the run does not hold, a catalog table,
        a figure no ledger holds and a constant `room.constants` lacks; with `recorded`,
        also a typed value the module docstring does not allow."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("the statement is empty")
        self.refresh()
        tree = json.loads(self.con.execute("SELECT json_serialize_sql(?)", [query]).fetchone()[0])
        if tree.get("error"):
            raise ValueError(f"the statement is one SELECT: {tree.get('error_message')}")
        if len(tree.get("statements") or []) != 1:
            raise ValueError("one statement per call - a schedule is one GROUP BY query")
        ctes: set[str] = set()
        bases: list[tuple[str, str]] = []
        figs: list[str] = []
        consts: list[tuple[str, str]] = []
        funcs: list[str] = []

        def walk(o):
            if isinstance(o, dict):
                if o.get("type") == "LIMIT_MODIFIER":
                    return
                cm = o.get("cte_map")
                if isinstance(cm, dict):
                    for kv in cm.get("map") or []:
                        ctes.add(str(kv.get("key", "")).lower())
                t = o.get("type")
                if t == "BASE_TABLE":
                    bases.append(((o.get("schema_name") or "").lower(), o.get("table_name") or ""))
                elif t == "TABLE_FUNCTION":
                    fn = (o.get("function") or {}).get("function_name", "?")
                    if fn not in TABLE_FUNCTIONS:
                        funcs.append(fn)
                fn = o.get("function_name") if o.get("class") == "FUNCTION" else None
                if fn == "fig" or fn in CONST_FUNCS:
                    args = [a.get("expression") or {} for a in o.get("arguments") or []]
                    lit = (args[0].get("literal") or {}) if len(args) == 1 \
                        and args[0].get("class") == "CONSTANT" else {}
                    if lit.get("kind") != "STRING":
                        raise ValueError(f"{fn}() takes one quoted name: "
                                         + ("fig('F.x.y')" if fn == "fig" else f"{fn}('name')"))
                    figs.append(lit["text"]) if fn == "fig" else consts.append((fn, lit["text"]))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(tree["statements"][0])
        have = {r[0]: r[1] for r in
                self.con.execute("SELECT name, unit FROM room.constants").fetchall()}
        for fn, name in consts:
            if name not in have:
                raise ValueError(f"{fn}('{name}'): room.constants holds no `{name}` - state it "
                                 f"first with Ledger.constants; it holds "
                                 f"{', '.join(sorted(have)) or 'none'}")
            want = CONST_FUNCS[fn]
            got = "date" if have[name] == "date" else "text" if have[name] == "text" else "number"
            if want != got:
                fix = {"number": "const", "date": "const_date", "text": "const_text"}[got]
                raise ValueError(f"{fn}('{name}'): `{name}` is a {got}; read it with "
                                 f"{fix}('{name}')")
        if recorded:
            dates = {r[0] for r in self.con.execute(
                "SELECT value FROM room.constants WHERE kind = 'declared' AND unit = 'date'")
                .fetchall()}
            faults = _typed(tree["statements"][0], dates | {_year_start(d) for d in dates})
            if faults:
                raise ValueError("the statement types " + "; ".join(faults) + " (scripts/sql.py)")
        if funcs:
            raise ValueError(f"table function(s) {sorted(set(funcs))}: a statement reads the "
                             f"run's tables by name (room.<id>, <check>.<name>); parse a file "
                             f"into the cache first (cache.write)")
        room, checks, unknown, catalog = [], [], [], []
        for schema, name in bases:
            if not schema and name.lower() in ctes:
                continue
            key = f"{schema}.{name}" if schema else name
            if schema == "countz":
                catalog.append(key)
            elif key not in self.tables:
                unknown.append(key)
            elif self.tables[key]["kind"] == "source":
                room.append(key) if key not in room else None
            else:
                checks.append(key) if key not in checks else None
        if catalog:
            raise ValueError(f"{sorted(set(catalog))}: a recorded statement reads room.<id>, "
                             f"<check>.<name> and fig(); read the catalog with countz-sql")
        if unknown:
            raise ValueError(f"no table {sorted(set(unknown))} in this run; it holds "
                             f"{', '.join(sorted(self.tables)) or '(no tables)'}")
        held = {r[0] for r in self.con.execute("SELECT id FROM countz.figures").fetchall()}
        missing = sorted({f for f in figs if f not in held})
        if missing:
            raise ValueError(f"fig({', '.join(missing)}): no ledger holds it yet - mint it "
                             f"first, or name the producing check's figure id exactly")
        m = ID_LIKE.search(QUOTED.sub("''", query))
        if m:
            raise ValueError(f"`{m.group(0)}...` outside a quoted string reads as a ledger id "
                             f"(EVIDENCE.md § 0) in the figure's expression - write the alias "
                             f"in lower case")
        return {"tables": room, "checks": checks, "figures": list(dict.fromkeys(figs)),
                "constants": list(dict.fromkeys(n for _, n in consts))}

    def roots(self, lin: dict) -> dict:
        """`lin` with every derived check table replaced by what its statement read, down
        to room tables, item tables, figures and constants."""
        out = {"tables": [], "items": [], "figures": list(lin["figures"]),
               "constants": list(lin.get("constants") or [])}
        seen: set[str] = set()

        def add(kind, x):
            if x not in out[kind]:
                out[kind].append(x)

        def walk(names):
            for t in names:
                if t in seen:
                    continue
                seen.add(t)
                info = self.tables[t]
                reads = (info["meta"] or {}).get("reads") if info["kind"] == "derived" else None
                if info["kind"] == "derived" and reads:
                    for x in reads.get("tables", []):
                        add("tables", x)
                    for x in reads.get("figures", []):
                        add("figures", x)
                    for x in reads.get("constants", []):
                        add("constants", x)
                    walk([c for c in reads.get("checks", []) if c in self.tables])
                else:
                    add("items", t)
        for x in lin["tables"]:
            add("tables", x)
        walk(lin["checks"])
        return out

    # -- running -------------------------------------------------------------------------
    def _run(self, query: str):
        try:
            return self.con.execute(query)
        except Exception as exc:
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            raise ValueError(f"the statement did not run: {first}") from exc

    def rows(self, query: str) -> tuple[list[str], list[tuple]]:
        """(column names, rows) of one SELECT, after `lineage` passes it."""
        self.lineage(query)
        cur = self._run(query)
        return [d[0] for d in cur.description], cur.fetchall()

    def frame(self, query: str):
        """One SELECT's result as a polars DataFrame, typed as DuckDB returns it."""
        pl = cache._pl()
        self.lineage(query)
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "result.parquet"
            self._run(f"COPY ({query.strip().rstrip(';')}) TO {_literal(out)} (FORMAT parquet)")
            return pl.read_parquet(out)

    def create(self, check: str, name: str, body: str, *, replace: bool,
               described: bool = False) -> dict:
        """`CREATE [OR REPLACE] TABLE <check>.<name> AS <body>`: the rows to
        `tables/<check>/<name>.parquet`, with the statement and what it reads. `described`:
        a COMMENT ON TABLE for it follows in the same call."""
        if check in RESERVED or not CHECK.fullmatch(check):
            raise ValueError(f"schema {check!r}: a check writes its own schema, named by its "
                             f"check id; room and countz are read only")
        if not NAME.fullmatch(name):
            raise ValueError(f"table {name!r}: a lower-case name, [a-z0-9][a-z0-9_]*")
        key = f"{check}.{name}"
        have = self.tables.get(key)
        if have and have["kind"] == "item":
            raise ValueError(f"{key} is an item table (checks/{check}-{name}.csv); name the "
                             f"table another way")
        if have and not replace:
            raise ValueError(f"{key} exists; CREATE OR REPLACE TABLE replaces it")
        lin = self.lineage(body, recorded=True)
        if key in lin["checks"]:
            raise ValueError(f"{key} reads itself")
        df = self.frame(body)
        was = (have or {}).get("meta") or {}
        if not described and not was.get("description"):
            raise ValueError(f"{key}: a check's table says what one row of it is - follow the "
                             f"CREATE with COMMENT ON TABLE {key} IS 'One row per ...' in the "
                             f"same run_sql call")
        notes = {c["name"]: c.get("description") for c in was.get("columns") or []}
        meta = {"schema": TABLE_SCHEMA, "id": key, "check": check, "name": name,
                "description": was.get("description"), "sql": body.strip(), "reads": lin,
                "engine": engine(), "row_count": df.height,
                "columns": [{"name": c, "description": notes.get(c)} for c in df.columns],
                "content_sha256": cache.content_sha256(df), "written_at": cache._now()}
        self._save(self.run_dir / TABLES_DIR / check / f"{name}.parquet", df, meta)
        return {"table": key, "rows": df.height, "columns": df.columns}

    def _save(self, out: pathlib.Path, df, meta: dict) -> None:
        tmp = cache._tmp_beside(out)
        try:
            df.write_parquet(tmp, metadata={cache.META: json.dumps(meta, ensure_ascii=False)})
            tmp.replace(out)
        finally:
            tmp.unlink(missing_ok=True)
        write_catalog(self.run_dir)
        self.refresh()

    def comment(self, check: str, name: str, column: str | None, text: str) -> dict:
        """`COMMENT ON TABLE | COLUMN`: the description of a check's own table or column."""
        key = f"{check}.{name}"
        t = self.tables.get(key)
        if t is None or t["kind"] != "derived":
            raise ValueError(f"{key}: COMMENT ON describes a table this run made with "
                             f"CREATE TABLE ... AS SELECT")
        meta = dict(t["meta"])
        if column is None:
            meta["description"] = text.strip() or None
        else:
            cols = [dict(c) for c in meta["columns"]]
            hit = [c for c in cols if c["name"] == column]
            if not hit:
                raise ValueError(f"{key} has no column {column!r}; it has "
                                 f"{[c['name'] for c in cols]}")
            hit[0]["description"] = text.strip() or None
            meta["columns"] = cols
        self._save(t["path"], cache._pl().read_parquet(t["path"]), meta)
        return {"table": key, "column": column}


_DBS: dict[pathlib.Path, Db] = {}


def _run_dir(run_dir) -> pathlib.Path:
    if run_dir is not None:
        return pathlib.Path(run_dir).resolve()
    here = pathlib.Path(os.getcwd()).resolve()
    for d in (here, *here.parents):
        if (d / "run.json").is_file():
            return d
    raise ValueError(f"no run.json in {here} or above; run from the run directory, or pass "
                     f"run_dir")


def db(run_dir=None) -> Db:
    """The run's connection, made once per process."""
    rd = _run_dir(run_dir)
    if rd not in _DBS:
        _DBS[rd] = Db(rd)
    return _DBS[rd]


def _bare(text: str) -> str:
    """The statement without the comment lines DuckDB attaches after its `;`."""
    lines = text.rstrip().splitlines()
    while lines and (not lines[-1].strip() or lines[-1].strip().startswith("--")):
        lines.pop()
    return "\n".join(lines).strip()


def run_sql(sql: str, run_dir=None):
    """Run SQL over the run's tables. Statements run in order; the last one's result is
    returned: a SELECT's rows as a polars DataFrame, a CREATE's {table, rows, columns}, a
    COMMENT's {table, column}."""
    d = db(run_dir)
    result = None
    statements = [(st, _bare(st.query)) for st in d.con.extract_statements(sql)]
    described = set()
    for _, text in statements:
        c = COMMENT.fullmatch(text)
        if c and c.group("what").upper() == "TABLE" and c.group("text").strip():
            described.add(f"{_unquote(c.group('schema'))}.{_unquote(c.group('name'))}")
    for st, text in statements:
        m, c = CREATE.fullmatch(text), COMMENT.fullmatch(text)
        if m:
            schema, name = _unquote(m.group("schema")), _unquote(m.group("name"))
            result = d.create(schema, name, m.group("body"), replace=bool(m.group("replace")),
                              described=f"{schema}.{name}" in described)
        elif c:
            result = d.comment(_unquote(c.group("schema")), _unquote(c.group("name")),
                               _unquote(c.group("col")) if c.group("col") else None,
                               c.group("text").replace("''", "'"))
        elif st.type.name == "SELECT":
            result = d.frame(text)
        else:
            raise ValueError(f"{st.type.name}: run_sql runs SELECT, CREATE [OR REPLACE] TABLE "
                             f"<check>.<name> AS SELECT, and COMMENT ON TABLE | COLUMN")
    return result


# -- minting -------------------------------------------------------------------------------
def _inputs(L, d: Db, lin: dict) -> list[dict]:
    """One input per room table, item table and figure the statement reaches; each table
    cited once in L."""
    import evidence
    from figures import check_output, declared, figure, room
    done = getattr(L, "_sql_cited", None)
    if done is None:
        done = L._sql_cited = set()
    r = d.roots(lin)
    out = []
    for t in r["tables"]:
        tid = t.removeprefix("room.")
        cid = f"E.{L.check}.{tid}"
        if cid not in done:
            L.cite(evidence.span(tid, run_dir=L.run_dir, id=cid,
                                 note="Rows selected by the SQL of each figure that cites it."))
            done.add(cid)
        out.append(room(tid, cid))
    for t in r["items"]:
        check, _, name = t.partition(".")
        cid = f"E.{L.check}.{check}-{name}"
        if cid not in done:
            L.cite(evidence.span(f"checks/{check}-{name}.csv", run_dir=L.run_dir, id=cid,
                                 note="Rows selected by the SQL of each figure that cites it."))
            done.add(cid)
        out.append(check_output(f"{check}-{name}", cid))
    for f in r["figures"]:
        out.append(figure(f, f))
    rows = {x[0]: dict(zip((c for c, _ in CONSTANTS_COLUMNS), x)) for x in constant_rows(L.run_dir)}
    for n in r["constants"]:
        c = rows.get(n) or {}
        if c.get("kind") == "stated" and c.get("citation_id"):
            out.append(room(f"const.{n}", c["citation_id"]))
        elif c.get("kind") == "declared":
            out.append(declared(f"const.{n}", f"params.{n.split('__')[0]}"))
    return out


def _number(v, where: str):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if v is None or isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    raise ValueError(f"{where}: the value column holds {type(v).__name__} {v!r}, not a number")


def _rows(L, query: str, need: tuple[str, ...]) -> tuple[Db, dict, list[dict]]:
    d = db(L.run_dir)
    d.attach(L)
    lin = d.lineage(query, recorded=True)
    names, rows = d.rows(query)
    missing = [c for c in need if c not in names]
    if missing:
        raise ValueError(f"the statement returns {names}; it needs the column(s) {missing}")
    recs = [dict(zip(names, r)) for r in rows]
    if not recs:
        raise ValueError("the statement returned no rows - nothing to mint; a population "
                         "measured empty is one row with zero_basis")
    ids = [r["id"] for r in recs]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"id(s) {dup} repeat - one row per entry")
    return d, lin, recs


def _all_or_none(L, ids: list[str], mint) -> None:
    saved = {k: L.entries.get(k) for k in ids}
    done = []
    try:
        for i in ids:
            mint(i)
            done.append(i)
    except Exception:
        for k in done:
            L.minted.discard(k)
            if saved.get(k) is None:
                L.entries.pop(k, None)
            else:
                L.entries[k] = saved[k]
        raise


FIGURE_COLUMNS = ("id", "label", "unit", "value")
FIGURE_OPTIONAL = ("population", "zero_basis", "disposition", "caveats")


def figures(L, query: str, **kw) -> list[str]:
    """Mint one figure per row of one SELECT (`Ledger.figures`; module docstring). `kw`
    passes to `Ledger.fig` for every row."""
    if "expression" in kw or "inputs" in kw:
        raise ValueError("`expression` and `inputs` come from the statement; do not pass them")
    d, lin, recs = _rows(L, query, FIGURE_COLUMNS)
    extra = sorted(set(recs[0]) - set(FIGURE_COLUMNS) - set(FIGURE_OPTIONAL))
    if extra:
        raise ValueError(f"column(s) {extra}: a figure row has {list(FIGURE_COLUMNS)} and "
                         f"optionally {list(FIGURE_OPTIONAL)}")
    ins = _inputs(L, d, lin)
    text = query.strip()
    by = {r["id"]: r for r in recs}

    def mint(fid):
        r = by[fid]
        opt = {k: r[k] for k in FIGURE_OPTIONAL if r.get(k) is not None}
        if "caveats" in opt:
            opt["caveats"] = list(opt["caveats"])
        L.fig(fid, r["label"], _number(r["value"], fid), r["unit"],
              f"{text}\n-- row: id = {_literal(fid)}", ins,
              sql={"engine": engine(), "text": text, "key": {"id": fid}, "value": "value",
                   "reads": lin},
              **{**kw, **opt})
    ids = sorted(by)
    _all_or_none(L, ids, mint)
    for fid in ids:
        e = L.entries[fid]
        d.hold((fid, L.check, e["label"], _float(e.get("value")), e["unit"], text), lin)
    return ids


def populations(L, query: str) -> list[str]:
    """Mint one `P.` entry per row of one SELECT (`Ledger.populations`; module docstring)."""
    d, lin, recs = _rows(L, query, ("id", "label", "total_n", "included_n"))
    extra = sorted(set(recs[0]) - {"id", "label", "total_n", "included_n", "exclusions"})
    if extra:
        raise ValueError(f"column(s) {extra}: a population row has id, label, total_n, "
                         f"included_n and optionally exclusions")
    text = query.strip()
    by = {r["id"]: r for r in recs}
    cits = [i["citation_id"] for i in _inputs(L, d, lin) if i.get("citation_id")]

    def mint(pid):
        r = by[pid]
        exc = [dict(x) for x in (r.get("exclusions") or [])]
        L.population(pid, r["label"], r["total_n"], r["included_n"], exclusions=exc,
                     citations=cits,
                     sql={"engine": engine(), "text": text, "key": {"id": pid}, "reads": lin})
    ids = sorted(by)
    _all_or_none(L, ids, mint)
    return ids


TEXT_SUFFIXES = frozenset({".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml",
                           ".html", ".htm", ".eml"})
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"], 1)}
NUMBER_IN = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(%|percent\b|per cent\b|"
                       r"thousand\b|million\b|billion\b|[kKmMbB]\b)?")
DATE_IN = re.compile(r"(?P<iso>\d{4}-\d{2}-\d{2})|(?P<mdy>(?P<m1>[A-Za-z]{3,9})\.?\s+(?P<d1>\d{1,2}),?"
                     r"\s+(?P<y1>\d{4}))|(?P<dmy>(?P<d2>\d{1,2})\s+(?P<m2>[A-Za-z]{3,9})\.?,?\s+"
                     r"(?P<y2>\d{4}))|(?P<us>(?P<m3>\d{1,2})/(?P<d3>\d{1,2})/(?P<y3>\d{4}))")
CONSTANT_FIELDS = ("name", "value", "unit", "file", "source", "file_role", "locator", "quote",
                   "basis")


def _plain_text(s: str) -> str:
    """Text as a quote is matched against it: emphasis marks dropped, spaces collapsed,
    typographic quotes and dashes made plain."""
    s = s.replace("**", "").replace("__", "").replace("`", "")
    s = s.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                                   "–": "-", "—": "-", " ": " "}))
    return " ".join(s.split())


def _document_text(path: pathlib.Path) -> str:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".docx":
        import zipfile
        import peek
        with zipfile.ZipFile(path) as z:
            return peek._xml_text(z.read("word/document.xml"), "w:t")
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError(f"{path.name}: no PDF text reader in this environment; state "
                             f"the value as `chosen` with its basis citing the page")
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    raise ValueError(f"{path.name}: a quote is checked in a text, .docx or .pdf file; state the "
                     f"value as `chosen` with its basis naming where the file states it")


def _in_quote(value: str, unit: str, quote: str) -> bool:
    """Whether the quote shows the value: the number (a percent for a share), the date in
    any common form, or the text."""
    if unit == "text":
        return value.casefold() in quote.casefold()
    if unit == "date":
        want = datetime.date.fromisoformat(value)
        for m in DATE_IN.finditer(quote):
            try:
                if m.group("iso"):
                    got = datetime.date.fromisoformat(m.group("iso"))
                elif m.group("us"):
                    got = datetime.date(int(m.group("y3")), int(m.group("m3")), int(m.group("d3")))
                else:
                    mon, day, yr = (m.group("m1"), m.group("d1"), m.group("y1")) if m.group("mdy") \
                        else (m.group("m2"), m.group("d2"), m.group("y2"))
                    month = next((i for k, i in MONTHS.items()
                                  if len(mon) >= 3 and k.startswith(mon.lower())), None)
                    if month is None:
                        continue
                    got = datetime.date(int(yr), month, int(day))
            except ValueError:
                continue
            if got == want:
                return True
        return False
    want = decimal.Decimal(value)
    scale = {"%": decimal.Decimal("0.01"), "percent": decimal.Decimal("0.01"),
             "per cent": decimal.Decimal("0.01"), "thousand": 1000, "k": 1000,
             "million": 10 ** 6, "m": 10 ** 6, "billion": 10 ** 9, "b": 10 ** 9}
    for m in NUMBER_IN.finditer(quote):
        n = decimal.Decimal(m.group(1).replace(",", "") + (m.group(2) or ""))
        k = (m.group(3) or "").lower()
        if n == want or (k and n * decimal.Decimal(scale[k]) == want):
            return True
    return False


def constants(L, rows) -> list[str]:
    """Write a check's constants to `constants/<check>.json`, replacing what the check
    wrote before (`Ledger.constants`). Each row is a dict: `name`, `value`, `unit` (a
    currency, a figure unit, `date` or `text`) and either
    - `file`, `source`, `file_role`, `locator` and `quote`: a value a document states.
      The quote is the document's own words around the value, at most 300 characters; it
      must be in the file and show the value. Cited as the passage `E.<check>.const.<name>`.
    - `basis`: a value the step chose, with why.
    Returns the names. A refused call writes nothing."""
    if isinstance(rows, dict):
        rows = [rows]
    run_dir = pathlib.Path(L.run_dir).resolve()
    taken = {r[0]: r for r in constant_rows(run_dir) if r[9] != L.check}
    out, cits, seen = [], [], set()
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError(f"constant {r!r}: a dict with name, value, unit and a source")
        extra = sorted(set(r) - set(CONSTANT_FIELDS))
        name = r.get("name")
        if extra:
            raise ValueError(f"constant {name!r}: field(s) {extra}; a constant has "
                             f"{', '.join(CONSTANT_FIELDS)}")
        if not isinstance(name, str) or not CONSTANT_NAME.fullmatch(name) or "__" in name:
            raise ValueError(f"constant name {name!r}: lower case, [a-z][a-z0-9_]*, at most "
                             f"60 characters, no `__`")
        if name in seen:
            raise ValueError(f"constant `{name}` twice in this call")
        seen.add(name)
        if name in taken:
            who = taken[name][9] or "the plan"
            raise ValueError(f"constant `{name}` is {taken[name][3]} by {who}; read it with "
                             f"const('{name}'), or name this one another way")
        unit = r.get("unit")
        if unit not in CONSTANT_UNITS:
            raise ValueError(f"constant `{name}`: unit {unit!r} - a currency code, one of "
                             f"{', '.join(style.OTHER_UNITS)}, `date` or `text`")
        value = _canon(r.get("value"), unit)
        stated = any(r.get(k) for k in ("file", "quote", "locator"))
        if stated == bool(r.get("basis")):
            raise ValueError(f"constant `{name}`: give either where a document states it "
                             f"(file, source, file_role, locator, quote) or the step's basis "
                             f"for choosing it")
        if not stated:
            out.append((name, value, unit, "chosen", None, None, None, None,
                        str(r["basis"]).strip(), L.check, None, None))
            continue
        for k in ("file", "file_role", "locator", "quote"):
            if not isinstance(r.get(k), str) or not r[k].strip():
                raise ValueError(f"constant `{name}`: a stated value needs `{k}`")
        if r["file_role"] not in cache.FILE_ROLES:
            raise ValueError(f"constant `{name}`: file_role {r['file_role']!r} - one of "
                             f"{', '.join(sorted(cache.FILE_ROLES))}")
        path, sid, rel = cache.resolve_file(run_dir, r["file"], r.get("source"))
        quote = _plain_text(r["quote"])
        if len(quote) > 300:
            raise ValueError(f"constant `{name}`: the quote is {len(quote)} characters; quote "
                             f"the words around the value, at most 300")
        if quote not in _plain_text(_document_text(path)):
            raise ValueError(f"constant `{name}`: the quote is not in {rel}, word for word")
        if not _in_quote(value, unit, quote):
            raise ValueError(f"constant `{name}`: the quote does not show {value} ({unit}); "
                             f"quote the words that state it")
        cid = f"E.{L.check}.const.{name}"
        cits.append({"id": cid, "kind": "passage", "file": rel, "source": sid,
                     "file_role": r["file_role"], "locator": r["locator"].strip(),
                     "quote": quote, "read_at": datetime.date.today().isoformat()})
        out.append((name, value, unit, "stated", rel, sid, r["locator"].strip(), quote, None,
                    L.check, cid, cache.sha256(path)))
    recs = [dict(zip((c for c, _ in CONSTANTS_COLUMNS), x)) for x in out]
    dest = run_dir / CONSTANTS_DIR / f"{L.check}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache._atomic(dest, json.dumps({"schema": CONSTANTS_SCHEMA, "check": L.check,
                                    "written_at": cache._now(), "rows_sha256": _rows_sha256(recs),
                                    "rows": recs}, indent=1, ensure_ascii=False) + "\n")
    stale = {k for k in L.citations if k.startswith(f"E.{L.check}.const.")}
    L.citations = {k: v for k, v in L.citations.items() if k not in stale}
    L.minted -= stale
    if cits:
        L.cite(*cits)
    write_catalog(run_dir)
    if run_dir in _DBS:
        _DBS[run_dir].refresh()
    return [x[0] for x in out]


def reperform(run_dir, id: str) -> str:
    """Every step behind a figure or table computed in SQL, in the order a re-performer
    runs them, one per line: the steps `lineage(id)` lists - each parsed table with its
    file, sheet, rows and control total, then each statement with the row it yields and
    its value."""
    d = db(run_dir)
    d.refresh()
    cur = d.con.execute("SELECT * FROM lineage(?)", [id])
    names = [c[0] for c in cur.description]
    out = []
    for r in (dict(zip(names, x)) for x in cur.fetchall()):
        if r["kind"] == "source":
            where = ", ".join(x for x in (r["file"], r["sheet"] and f"sheet {r['sheet']}",
                                          r["rows_read"] and f"rows {r['rows_read']}") if x)
            ctl = f"; control total {r['control_column']} {r['control_total']}" \
                if r["control_column"] else ""
            out.append(f"{r['step']}. {r['node']}: read from {where}{ctl}")
        elif r["kind"] == "constant":
            name, unit = r["node"].removeprefix("const:"), f" {r['unit']}" if r["unit"] else ""
            how = {"stated": f"stated in {r['file']}, {r['locator']}: \"{r['quote']}\"",
                   "declared": f"declared in {r['file']}, {r['locator']}",
                   "chosen": f"chosen: {r['basis']}"}.get(r["constant_kind"], "")
            out.append(f"{r['step']}. constant {name} = {r['value']}{unit}, {how}")
        elif r["statement"] and r["row_key"]:
            out.append(f"{r['step']}. {r['node']}: {' '.join(r['statement'].split())} - the row "
                       f"where {r['row_key']} holds {r['value']}")
        elif r["statement"]:
            out.append(f"{r['step']}. CREATE TABLE {r['node']} AS "
                       f"{' '.join(r['statement'].split())}")
        else:
            out.append(f"{r['step']}. {r['node']}: no statement ({r['kind']})")
    return "\n".join(out)


# -- verify --------------------------------------------------------------------------------
def _agrees(stored, now, unit: str) -> bool:
    if stored is None or now is None:
        return stored is None and now is None
    a, b = float(stored), float(now)
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    if style.is_money(unit):
        return abs(a - b) <= 0.5 * 10 ** -style.minor_units(unit) + 1e-9
    if unit == "count":
        return round(a) == round(b)
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def _keyed(names, rows, key: dict):
    def norm(x):
        return x.isoformat() if isinstance(x, (datetime.date, datetime.datetime)) else x
    return [r for r in rows if all(norm(r[names.index(k)]) == v for k, v in key.items())]


def _outside_sql(e: dict, cited: dict[str, str]) -> bool:
    """A ledger entry computed in Python where SQL should have computed it. `cited` maps a
    citation id to its kind."""
    if isinstance(e.get("sql"), dict):
        return False
    if str(e.get("id", "")).startswith("P."):
        return True
    if e.get("tie") or e.get("value") is None:
        return False
    ins = e.get("inputs") or []
    return not (e.get("disposition") == "as_stated" and ins and all(
        i.get("source_type") == "room_file" and cited.get(i.get("citation_id")) == "cell"
        for i in ins))


def verify(run_dir, check: str | None = None) -> dict:
    """Re-run every statement and compare (module docstring, verify)."""
    import yaml
    run_dir = pathlib.Path(run_dir).resolve()
    wp = run_dir / "workpapers"
    failures = []
    d = Db(run_dir)
    for t in d.tables.values():
        if t["kind"] == "item" and (check is None or t["check"] == check) \
                and not (t["meta"] or {}).get("sql"):
            failures.append(f"{t['name']}: an item table written from rows computed outside "
                            f"SQL - write it with items.write_items(..., sql=<SELECT>)")
    tabs = [t for t in d.tables.values() if t["kind"] == "derived"
            and (check is None or t["check"] == check)]
    for t in tabs:
        m = t["meta"] or {}
        if not m.get("sql"):
            failures.append(f"{t['name']}: no statement in its metadata - make it with "
                            f"CREATE TABLE ... AS SELECT")
            continue
        held = cache._pl().read_parquet(t["path"])
        if cache.content_sha256(held) != m.get("content_sha256"):
            failures.append(f"{t['name']}: its rows changed after its statement wrote them")
            continue
        try:
            df = d.frame(m["sql"])
        except ValueError as exc:
            failures.append(f"{t['name']}: its statement no longer runs - {exc}")
            continue
        if cache.content_sha256(df) != m.get("content_sha256"):
            failures.append(f"{t['name']}: its statement now returns other rows ({df.height}, "
                            f"recorded {m.get('row_count')}) - re-run the check, or fix what moved")
    entries = []
    cited = {c.get("id"): c.get("kind") for f in sorted(wp.glob("evidence-*.yaml"))
             for c in yaml.safe_load(f.read_text(encoding="utf-8")) or [] if isinstance(c, dict)}
    for f in sorted(wp.glob("figures-*.yaml")):
        if check is not None and f.name != f"figures-{check}.yaml":
            continue
        for e in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            if isinstance(e, dict) and isinstance(e.get("sql"), dict):
                entries.append((f.name, e))
            elif isinstance(e, dict) and _outside_sql(e, cited):
                how = "Ledger.populations" if str(e.get("id")).startswith("P.") else "Ledger.figures"
                failures.append(f"{e.get('id')} ({f.name}): computed outside SQL - mint it "
                                f"with {how}(<SELECT>); a value a passage or the plan states "
                                f"enters as a constant, const('name')")
    results: dict[str, tuple | str] = {}
    for _, e in entries:
        t = e["sql"].get("text") or ""
        if t not in results:
            try:
                results[t] = d.rows(t)
            except ValueError as exc:
                results[t] = str(exc)
    for led, e in entries:
        s, eid = e["sql"], e["id"]
        res = results[s.get("text") or ""]
        if isinstance(res, str):
            failures.append(f"{eid} ({led}): its statement no longer runs - {res}")
            continue
        names, rows = res
        hit = _keyed(names, rows, s["key"]) if s.get("key") else rows
        if len(hit) != 1:
            failures.append(f"{eid} ({led}): {len(hit)} rows now carry key {s.get('key')}")
            continue
        r = hit[0]
        if eid.startswith("P."):
            now = {k: r[names.index(k)] for k in ("total_n", "included_n")}
            if now != {k: e.get(k) for k in now}:
                failures.append(f"{eid} ({led}): recorded {e.get('total_n')}/"
                                f"{e.get('included_n')}, its statement now returns "
                                f"{now['total_n']}/{now['included_n']}")
            continue
        col = s.get("value") or "value"
        if col not in names:
            failures.append(f"{eid} ({led}): no column {col!r} in the result")
            continue
        now = _float(r[names.index(col)]) if r[names.index(col)] is not None else None
        if not _agrees(e.get("value"), now, str(e.get("unit") or "")):
            failures.append(f"{eid} ({led}): recorded {e.get('value')!r}, its statement now "
                            f"returns {now!r} - re-run the check, or fix what moved")
    for p in sorted((run_dir / CONSTANTS_DIR).glob("*.json")):
        if check is not None and p.stem != check:
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        if _rows_sha256(doc.get("rows") or []) != doc.get("rows_sha256"):
            failures.append(f"constants of {p.stem}: changed after Ledger.constants wrote them")
            continue
        for r in doc.get("rows") or []:
            if r["kind"] != "stated":
                continue
            try:
                path = cache.resolve_file(run_dir, r["file"], r["source"])[0]
            except ValueError as exc:
                failures.append(f"constant {r['name']} ({p.stem}): {exc}")
                continue
            if cache.sha256(path) != r["sha256"]:
                failures.append(f"constant {r['name']} ({p.stem}): {r['file']} changed since "
                                f"it was quoted")
            elif r["quote"] not in _plain_text(_document_text(path)):
                failures.append(f"constant {r['name']} ({p.stem}): {r['file']} no longer "
                                f"holds the quote")
    for f in sorted(wp.glob("evidence-*.yaml")):
        if f.name.startswith("evidence-profile-"):
            continue
        if check is not None and f.name != f"evidence-{check}.yaml":
            continue
        for e in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            if isinstance(e, dict) and e.get("kind") == "span" \
                    and e.get("file_role") != "run_artifact" and not e.get("cache_id"):
                failures.append(f"{e.get('id')} ({f.name}): a data-room span with no cache_id - "
                                f"the table was parsed outside the cache; write it with "
                                f"cache.write and read it by SQL")
    return {"failures": failures, "figures": len(entries), "tables": len(tabs),
            "statements": len(results) + len(tabs)}


# -- command line --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("run_dir", type=pathlib.Path)
    v.add_argument("--check")
    c = sub.add_parser("catalog")
    c.add_argument("run_dir", type=pathlib.Path)
    a = ap.parse_args()
    try:
        if a.cmd == "catalog":
            print(write_catalog(a.run_dir))
            return 0
        r = verify(a.run_dir, a.check)
    except ValueError as exc:
        print(f"sql.py: {exc}", file=sys.stderr)
        return 1
    for f in r["failures"]:
        print(f"FAIL: {f}")
    print(f"{r['figures']} figure(s) and population(s), {r['tables']} table(s) over "
          f"{r['statements']} statement(s): {len(r['failures'])} failure(s)")
    return 1 if r["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
