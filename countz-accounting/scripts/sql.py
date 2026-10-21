#!/usr/bin/env python3
"""Compute figures with SQL (DuckDB) over the run's cache. The statement is stored as the
figure's `expression`, and `verify` re-runs it.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    import sql
    from figures import Ledger

    db = sql.connect(RUN)
    L = Ledger(RUN, "r5_position")
    L.fig_sql(db, "F.r5.past_due.2025-06", "Receivable past due at 30 June 2025", "usd",
              "SELECT sum(open_amount) FROM aging_2025_06_30 WHERE due_date < DATE '2025-06-30'")
    L.figs_sql(db, "F.r5.sales.{month}", "Billed credit sales, {month}", "usd",
               "SELECT strftime(invoice_date, '%Y-%m') AS month, sum(amount) AS value "
               "FROM inv_2025 GROUP BY month", key="month")
    L.figs_sql(db, "F.r5.credits.{customer_id}", "Credit memos, {customer_id}", "usd",
               "SELECT customer_id, sum(credit) AS value FROM inv_2025 GROUP BY customer_id",
               key="customer_id", population="P.r5.customers", zero_basis="measured_zero")
    L.fig_sql(db, "F.r5.dso3.2025-06", "DSO at 30 June 2025", "days",
              "SELECT fig('F.r5.numerator.2025-06') / fig('F.r5.sales3.2025-06') * 91")
    rows = db.frame("SELECT customer_id, sum(open_amount) AS amount FROM aging_2025_06_30 "
                    "GROUP BY customer_id")          # polars DataFrame, for an item table or a tab
    L.write()

A statement reads cache tables by id, item tables as `checks."<check>-<table>"` (typed as
`write_items` was given them; a table written after `connect` is read on the next
statement), and figures as `fig('F.x')`: every ledger's, and every figure this run's
`Ledger` has minted so far. It is one SELECT. File functions (`read_csv`, ...) are
refused: parse a file into the cache first. Aliases are lower case, because an upper-case
`P.x` reads as a ledger id in the expression.

`fig_sql` takes a statement that returns one row. `figs_sql` takes a GROUP BY: `key` names
the column(s) that fill the `{name}` placeholders, and `value` the figure's column (default
`value`); `zero_basis` applies to the rows whose value is zero or null. Each cites the
tables it reads once per ledger.

`verify(run_dir, check=None)` re-runs every statement and fails three things:
- a figure whose value changed (money beyond half its minor unit, a count by any amount,
  anything else beyond 1e-9);
- a statement that no longer runs;
- a data-room span with no `cache_id`.

    sql.py tables <run_dir>
    sql.py query <run_dir> "<select>" [--limit 20]
    sql.py profile <run_dir> <table>
    sql.py verify <run_dir> [--check <check>]        exit 1 on a failure

Run with `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cache  # noqa: E402  sibling: the parsed tables and their manifest
import style  # noqa: E402  sibling: a currency's minor units

ARTIFACTS = "checks"            # the schema the run's item tables sit in
ITEM_TABLE = re.compile(r"(?P<check>[a-z0-9][a-z0-9_]*)-(?P<table>[a-z0-9][a-z0-9_-]*)")
# An identifier that reads as a ledger id (EVIDENCE.md § 0) once string literals are blanked.
ID_LIKE = re.compile(r"(?<![\w.\"])[A-Z]{1,2}\.[A-Za-z0-9_]")
QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")


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


def _literal(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _float(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _ledger_figures(run_dir: pathlib.Path) -> list[tuple[str, object, str, str]]:
    """(id, value, unit, ledger file) for every figure entry in workpapers/figures-*.yaml."""
    import yaml
    out = []
    for f in sorted((run_dir / "workpapers").glob("figures-*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or []
        if not isinstance(doc, list):
            raise ValueError(f"{f}: the ledger is not a YAML list (EVIDENCE.md § 0)")
        for e in doc:
            if isinstance(e, dict) and str(e.get("id", "")).startswith("F."):
                out.append((e["id"], _float(e.get("value")), str(e.get("unit") or ""), f.name))
    return out


class Db:
    """One read-only DuckDB connection over a run: the cache's tables, the item tables and
    the figures. Build it with `connect`."""

    def __init__(self, run_dir):
        duckdb = _duckdb()
        self.run_dir = pathlib.Path(run_dir).resolve()
        self.con = duckdb.connect(":memory:")
        self.tables: dict[str, dict] = {}       # name as a query writes it -> what it is
        if (self.run_dir / cache.CACHE_DIR / cache.MANIFEST).is_file():
            for e in cache.manifest(self.run_dir)["files"]:
                p = self.run_dir / e["parquet"]
                self.con.execute(f"CREATE VIEW {_ident(e['id'])} AS "
                                 f"SELECT * FROM read_parquet({_literal(p)})")
                self.tables[e["id"]] = {"kind": "cache", "id": e["id"], "file": e["file"]}
        self.con.execute(f"CREATE SCHEMA {ARTIFACTS}")
        self._items: dict[str, tuple] = {}       # item table -> the file stats its view read
        self._refresh_items()
        self.con.execute("CREATE TABLE figures (id VARCHAR, value DOUBLE, unit VARCHAR, "
                         "ledger VARCHAR)")
        rows = _ledger_figures(self.run_dir)
        if rows:
            self.con.executemany("INSERT INTO figures VALUES (?, ?, ?, ?)", rows)
        self.con.execute("CREATE MACRO fig(i) AS (SELECT value FROM figures WHERE id = i)")
        self._held = {r[0]: (r[1], r[3]) for r in rows}
        self._ledgers: list = []                 # the Ledgers whose figures fig() reads

    def _refresh_items(self) -> None:
        """One view per item table in checks/, re-made when its files change. A table
        reads typed from the parquet `write_items` writes beside the CSV; a CSV newer than
        its parquet (edited by hand) reads as text with `amount` a number."""
        seen = set()
        for p in sorted((self.run_dir / "checks").glob("*-*.csv")):
            m = ITEM_TABLE.fullmatch(p.stem)
            if not m:
                continue
            seen.add(p.stem)
            pq = p.with_suffix(".parquet")
            typed = pq.is_file() and pq.stat().st_mtime_ns >= p.stat().st_mtime_ns
            stat = (p.stat().st_mtime_ns, p.stat().st_size,
                    pq.stat().st_mtime_ns if typed else None)
            if self._items.get(p.stem) == stat:
                continue
            if typed:
                body = f"SELECT * FROM read_parquet({_literal(pq)})"
            else:
                read = f"read_csv({_literal(p)}, all_varchar = true, header = true)"
                names = [c[0] for c in self.con.execute(f"SELECT * FROM {read} LIMIT 0").description]
                sel = "* REPLACE (CAST(amount AS DOUBLE) AS amount)" if "amount" in names else "*"
                body = f"SELECT {sel} FROM {read}"
            self.con.execute(f"CREATE OR REPLACE VIEW {ARTIFACTS}.{_ident(p.stem)} AS {body}")
            self._items[p.stem] = stat
            self.tables[f"{ARTIFACTS}.{p.stem}"] = {
                "kind": "artifact", "id": p.stem, "file": f"checks/{p.name}",
                "from_check": m.group("check")}
        for gone in set(self._items) - seen:
            self.con.execute(f"DROP VIEW IF EXISTS {ARTIFACTS}.{_ident(gone)}")
            del self._items[gone]
            del self.tables[f"{ARTIFACTS}.{gone}"]

    def attach(self, L) -> None:
        """Let `fig()` read the figures `L` mints, as it mints them."""
        if not any(x is L for x in self._ledgers):
            self._ledgers.append(L)

    def _sync(self) -> None:
        for L in self._ledgers:
            led = L.figures_path.name
            for fid, e in L.entries.items():
                if fid.startswith("F.") and self._held.get(fid) != (_float(e.get("value")), led):
                    self.hold(fid, e.get("value"), str(e.get("unit") or ""), led)

    # -- reading a statement -------------------------------------------------------------
    def lineage(self, query: str) -> dict:
        """What one SELECT reads, from its parse tree, without running it:
        {"tables": [cache ids], "artifacts": ["checks.<check>-<table>"], "figures": [F. ids]}.
        Refuses a statement that is not one SELECT, a file function, a table the run does
        not hold and a figure no ledger holds."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("the statement is empty")
        self._refresh_items()
        self._sync()
        tree = json.loads(self.con.execute("SELECT json_serialize_sql(?)", [query]).fetchone()[0])
        if tree.get("error"):
            raise ValueError(f"the statement is one SELECT: {tree.get('error_message')}")
        if len(tree.get("statements") or []) != 1:
            raise ValueError("one statement per call - a schedule is one GROUP BY query")
        ctes: set[str] = set()
        bases: list[tuple[str, str]] = []
        figs: list[str] = []
        funcs: list[str] = []

        def walk(o):
            if isinstance(o, dict):
                cm = o.get("cte_map")
                if isinstance(cm, dict):
                    for kv in cm.get("map") or []:
                        ctes.add(str(kv.get("key", "")).lower())
                t = o.get("type")
                if t == "BASE_TABLE":
                    bases.append((o.get("schema_name") or "", o.get("table_name") or ""))
                elif t == "TABLE_FUNCTION":
                    funcs.append((o.get("function") or {}).get("function_name", "?"))
                if o.get("class") == "FUNCTION" and o.get("function_name") == "fig":
                    args = [a.get("expression") or {} for a in o.get("arguments") or []]
                    lit = (args[0].get("literal") or {}) if len(args) == 1 \
                        and args[0].get("class") == "CONSTANT" else {}
                    if lit.get("kind") != "STRING":
                        raise ValueError("fig() takes one figure id as a quoted string: "
                                         "fig('F.x.y')")
                    figs.append(lit["text"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(tree["statements"][0])
        if funcs:
            raise ValueError(f"table function(s) {sorted(set(funcs))}: a query reads the cache's "
                             f"tables by name - parse a file into the cache first "
                             f"(cache.write, or evidence.span(frame=..., run_dir=...))")
        tables, artifacts, unknown = [], [], []
        for schema, name in bases:
            if not schema and (name.lower() in ctes or name == "figures"):
                continue
            key = f"{schema}.{name}" if schema else name
            if key not in self.tables:
                unknown.append(key)
            elif self.tables[key]["kind"] == "cache":
                tables.append(key) if key not in tables else None
            else:
                artifacts.append(key) if key not in artifacts else None
        if unknown:
            raise ValueError(f"no table {sorted(set(unknown))} in this run; a query reads "
                             f"{', '.join(sorted(self.tables)) or '(no tables)'}")
        missing = sorted({f for f in figs if f not in self._held})
        if missing:
            raise ValueError(f"fig({', '.join(missing)}): no ledger holds it yet - mint it "
                             f"first, or name the producing check's figure id exactly")
        shape = QUOTED.sub("''", query)
        m = ID_LIKE.search(shape)
        if m:
            raise ValueError(f"`{m.group(0)}...` outside a quoted string reads as a ledger id "
                             f"(EVIDENCE.md § 0) in the figure's expression - write the alias "
                             f"in lower case")
        return {"tables": tables, "artifacts": artifacts, "figures": list(dict.fromkeys(figs))}

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
        """One SELECT's result as a polars DataFrame, types as DuckDB returns them (via a
        temporary parquet - no pyarrow needed)."""
        pl = cache._pl()
        self.lineage(query)
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "result.parquet"
            self._run(f"COPY ({query.strip().rstrip(';')}) TO {_literal(out)} (FORMAT parquet)")
            return pl.read_parquet(out)

    def value(self, query: str, value: str | None = None):
        """The one number one SELECT returns: its only column, or the column `value`."""
        names, rows = self.rows(query)
        return _one_value(names, rows, value)

    def hold(self, fid: str, value, unit: str, ledger: str) -> None:
        """Make a figure just minted readable by `fig()` on this connection."""
        v = _float(value)
        self.con.execute("DELETE FROM figures WHERE id = ? AND ledger = ?", [fid, ledger])
        self.con.execute("INSERT INTO figures VALUES (?, ?, ?, ?)", [fid, v, unit, ledger])
        self._held[fid] = (v, ledger)


def connect(run_dir) -> Db:
    return Db(run_dir)


def _one_value(names: list[str], rows: list[tuple], value: str | None):
    if len(rows) != 1:
        raise ValueError(f"the statement returned {len(rows)} rows; a figure is one row - "
                         f"a schedule of figures is `figs` with a key")
    if value is None:
        if len(names) != 1:
            raise ValueError(f"the statement returned columns {names}; name the figure's "
                             f"column with `value=`")
        return rows[0][0]
    if value not in names:
        raise ValueError(f"no column {value!r} in the result; it has {names}")
    return rows[0][names.index(value)]


def _number(v, where: str):
    import datetime
    import decimal
    if v is None or isinstance(v, (int, float, decimal.Decimal)) and not isinstance(v, bool):
        return v
    if isinstance(v, (datetime.date, str, bool)):
        raise ValueError(f"{where}: the figure's column holds {type(v).__name__} {v!r}, "
                         f"not a number")
    return v


# -- minting -------------------------------------------------------------------------------
def _inputs(L, db: Db, lin: dict) -> list[dict]:
    """One input per table and figure the statement reads; each table cited once in L."""
    import evidence
    from figures import check_output, figure, room
    done = getattr(L, "_sql_cited", None)
    if done is None:
        done = L._sql_cited = set()
    out = []
    for t in lin["tables"]:
        cid = f"E.{L.check}.{t}"
        if cid not in done:
            L.cite(evidence.span(t, run_dir=L.run_dir, id=cid,
                                 note="Rows selected by the SQL of each figure that cites it."))
            done.add(cid)
        out.append(room(t, cid))
    for a in lin["artifacts"]:
        name = db.tables[a]["id"]
        cid = f"E.{L.check}.{name}"
        if cid not in done:
            L.cite(evidence.span(db.tables[a]["file"], run_dir=L.run_dir, id=cid,
                                 note="Rows selected by the SQL of each figure that cites it."))
            done.add(cid)
        out.append(check_output(name, cid))
    for f in lin["figures"]:
        out.append(figure(f, f))
    return out


def fig(L, db: Db, fid: str, label: str, unit: str, query: str, *, value: str | None = None,
        **kw) -> str:
    """One figure from one SELECT that returns one row (`Ledger.fig_sql`). `kw` passes to
    `Ledger.fig` (population, disposition, zero_basis, caveats, extras)."""
    if "expression" in kw or "inputs" in kw:
        raise ValueError(f"{fid}: the statement is the expression and its reads the inputs")
    db.attach(L)
    lin = db.lineage(query)
    names, rows = db.rows(query)
    v = _number(_one_value(names, rows, value), fid)
    ins = _inputs(L, db, lin)
    text = query.strip()
    out = L.fig(fid, label, v, unit, text, ins,
                sql={"engine": engine(), "text": text, "key": None, "value": value}, **kw)
    db.hold(fid, L.entries[fid]["value"], unit, L.figures_path.name)
    return out


def figs(L, db: Db, fid: str, label: str, unit: str, query: str, *, key, value: str = "value",
         population=None, zero_basis=None, **kw) -> list[str]:
    """One figure per row of one SELECT (`Ledger.figs_sql`): `key` (a column or a list of
    columns) fills the `{name}` placeholders of `fid`, `label` and a string `population`;
    `value` is the column holding each figure; `zero_basis` goes on the rows whose value is
zero or null. Every row is minted or none is."""
    if "expression" in kw or "inputs" in kw:
        raise ValueError(f"{fid}: the statement is the expression and its reads the inputs")
    keys = [key] if isinstance(key, str) else list(key)
    if not keys:
        raise ValueError(f"{fid}: `key` names the column(s) that tell the rows apart")
    db.attach(L)
    lin = db.lineage(query)
    names, rows = db.rows(query)
    for k in keys + [value]:
        if k not in names:
            raise ValueError(f"{fid}: no column {k!r} in the result; it has {names}")
    if not rows:
        raise ValueError(f"{fid}: the statement returned no rows - nothing to mint; a "
                         f"population measured empty is one figure with zero_basis")
    import datetime
    plan, seen = [], set()
    for r in rows:
        kv = {}
        for k in keys:
            x = r[names.index(k)]
            kv[k] = x.isoformat() if isinstance(x, datetime.date) else x
        t = tuple(kv[k] for k in keys)
        if t in seen:
            raise ValueError(f"{fid}: key {dict(zip(keys, t))} repeats - one row per figure")
        seen.add(t)
        try:
            one = fid.format(**{k: str(v) for k, v in kv.items()})
            lab = label.format(**{k: str(v) for k, v in kv.items()})
            pop = population.format(**{k: str(v) for k, v in kv.items()}) \
                if isinstance(population, str) else population
        except KeyError as exc:
            raise ValueError(f"{fid}: placeholder {exc} is not a key column {keys}") from exc
        plan.append((one, lab, pop, kv, _number(r[names.index(value)], one)))
    plan.sort(key=lambda p: tuple(str(p[3][k]) for k in keys))   # a GROUP BY has no order
    ins = _inputs(L, db, lin)
    text = query.strip()
    minted = []
    saved = {k: L.entries.get(k) for k, *_ in plan}
    try:
        for one, lab, pop, kv, v in plan:
            zb = zero_basis if v is None or v == 0 or v != v else None
            L.fig(one, lab, v, unit, f"{text}\n-- row: " + ", ".join(
                f"{k} = {_literal(x)}" for k, x in kv.items()), ins, population=pop,
                zero_basis=zb, sql={"engine": engine(), "text": text, "key": kv,
                                    "value": value}, **kw)
            minted.append(one)
    except Exception:
        for k in minted:                            # every row or none
            L.minted.discard(k)
            if saved.get(k) is None:
                L.entries.pop(k, None)
            else:
                L.entries[k] = saved[k]
        raise
    for one in minted:
        db.hold(one, L.entries[one]["value"], unit, L.figures_path.name)
    return minted


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


def verify(run_dir, check: str | None = None) -> dict:
    """Re-run every figure's query and compare (module docstring, verify)."""
    import yaml
    run_dir = pathlib.Path(run_dir).resolve()
    wp = run_dir / "workpapers"
    failures = []
    entries = []
    for f in sorted(wp.glob("figures-*.yaml")):
        if check is not None and f.name != f"figures-{check}.yaml":
            continue
        for e in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            if isinstance(e, dict) and isinstance(e.get("sql"), dict):
                entries.append((f.name, e))
    db = Db(run_dir)
    results: dict[str, tuple[list[str], list[tuple]] | str] = {}
    for _, e in entries:
        t = e["sql"].get("text") or ""
        if t not in results:
            try:
                results[t] = db.rows(t)
            except ValueError as exc:
                results[t] = str(exc)
    for led, e in entries:
        s, fid = e["sql"], e["id"]
        res = results[s.get("text") or ""]
        if isinstance(res, str):
            failures.append(f"{fid} ({led}): its query no longer runs - {res}")
            continue
        names, rows = res
        try:
            if s.get("key"):
                ks = list(s["key"])
                hit = [r for r in rows if all(
                    (r[names.index(k)].isoformat() if hasattr(r[names.index(k)], "isoformat")
                     else r[names.index(k)]) == s["key"][k] for k in ks)]
                if len(hit) != 1:
                    failures.append(f"{fid} ({led}): {len(hit)} rows now carry key {s['key']}")
                    continue
                now = hit[0][names.index(s.get("value") or "value")]
            else:
                now = _one_value(names, rows, s.get("value"))
        except ValueError as exc:
            failures.append(f"{fid} ({led}): {exc}")
            continue
        now = float(now) if now is not None and not isinstance(now, (int, float)) else now
        if not _agrees(e.get("value"), now, str(e.get("unit") or "")):
            failures.append(f"{fid} ({led}): recorded {e.get('value')!r}, its query now "
                            f"returns {now!r} - re-run the check, or fix what moved")
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
                                f"cache.write (or evidence.span(frame=..., run_dir=...)) and "
                                f"read it by SQL")
    return {"failures": failures, "figures": len(entries),
            "statements": len(results)}


# -- command line --------------------------------------------------------------------------
def _print_rows(names, rows, limit: int) -> None:
    print("\t".join(names))
    for r in rows[:limit]:
        print("\t".join("" if x is None else str(x) for x in r))
    if len(rows) > limit:
        print(f"... {len(rows) - limit} more row(s); {len(rows)} in all")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tables")
    t.add_argument("run_dir", type=pathlib.Path)
    q = sub.add_parser("query")
    q.add_argument("run_dir", type=pathlib.Path)
    q.add_argument("sql")
    q.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("profile")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("table")
    p.add_argument("--max-distinct", type=int, default=25)
    v = sub.add_parser("verify")
    v.add_argument("run_dir", type=pathlib.Path)
    v.add_argument("--check")
    a = ap.parse_args()
    try:
        if a.cmd == "verify":
            r = verify(a.run_dir, a.check)
            for f in r["failures"]:
                print(f"FAIL: {f}")
            print(f"{r['figures']} SQL figure(s) over {r['statements']} statement(s): "
                  f"{len(r['failures'])} failure(s)")
            return 1 if r["failures"] else 0
        db = Db(a.run_dir)
        if a.cmd == "tables":
            for name, d in sorted(db.tables.items()):
                n = db.con.execute(f"SELECT count(*) FROM {_qualified(name)}").fetchone()[0]
                print(f"{name}\t{d['kind']}\t{n} rows\t{d['file']}")
            print(f"figures\tledgers\t{len(db._held)} figure ids\tworkpapers/figures-*.yaml")
            return 0
        if a.cmd == "query":
            names, rows = db.rows(a.sql)
            _print_rows(names, rows, a.limit)
            return 0
        if a.table not in db.tables:
            print(f"no table {a.table!r}; `sql.py tables` lists them", file=sys.stderr)
            return 1
        tq = _qualified(a.table)
        cur = db.con.execute(f"SELECT column_name, column_type, min, max, approx_unique, "
                             f"null_percentage FROM (SUMMARIZE SELECT * FROM {tq})")
        names = [d[0] for d in cur.description]
        summ = cur.fetchall()
        _print_rows(names, summ, len(summ))
        nums = [r[0] for r in summ if re.match(r"(DOUBLE|FLOAT|DECIMAL|BIGINT|INTEGER|HUGEINT)",
                                               str(r[1]))]
        for col, typ, *_rest in summ:
            u = _rest[2] or 0
            if str(typ) == "VARCHAR" and 1 < u <= a.max_distinct:
                agg = "".join(f", sum({_ident(n)}) AS {_ident('sum_' + n)}" for n in nums)
                cur = db.con.execute(f"SELECT {_ident(col)}, count(*) AS n{agg} FROM {tq} "
                                     f"GROUP BY 1 ORDER BY n DESC")
                print(f"\n-- by {col}")
                _print_rows([d[0] for d in cur.description], cur.fetchall(), a.max_distinct)
        return 0
    except ValueError as exc:
        print(f"sql.py: {exc}", file=sys.stderr)
        return 1


def _qualified(name: str) -> str:
    schema, _, t = name.rpartition(".") if name.startswith(f"{ARTIFACTS}.") else ("", "", name)
    return f"{schema}.{_ident(t)}" if schema else _ident(t)


if __name__ == "__main__":
    raise SystemExit(main())
