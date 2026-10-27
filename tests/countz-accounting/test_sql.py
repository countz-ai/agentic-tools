#!/usr/bin/env python3
"""Self-test for scripts/sql.py (and the SQL path through cache.py, figures.py, items.py and
evidence.py).

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_sql.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import cache  # noqa: E402
import evidence  # noqa: E402
import items  # noqa: E402
import sql  # noqa: E402
from figures import Ledger  # noqa: E402
from items import write_items  # noqa: E402
from sql import run_sql  # noqa: E402


def _col(at, description, unit=None):
    c = {"at": at, "parse": "as written", "description": description}
    return {**c, "unit": unit} if unit else c


def main() -> int:
    import tempfile
    import yaml
    pl = cache._pl()
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
        tdp = pathlib.Path(td).resolve()
        room, rd = tdp / "room", tdp / "run"
        room.mkdir()
        rd.mkdir()
        (room / "inv.csv").write_text("id,month,amount,kind,start\n1,2025-05,100,INV,2025-01-01\n"
                                      "2,2025-05,50,CM,2025-01-01\n3,2025-06,200,INV,2025-03-01\n"
                                      "4,2025-06,25.5,INV,2025-06-01\n")
        (room / "terms.csv").write_text("kind,max_days\nINV,30\nCM,0\n")
        (room / "policy.md").write_text("# Fee policy\n\nThe **fee** is 10% of each invoice,\n"
                                        "effective March 1, 2025, under agreement NP-0042.\n")
        (rd / "plan").mkdir()
        (rd / "plan" / "r.json").write_text(json.dumps({"steps": [
            {"id": "t1", "params": {"materiality": 1000.5, "period_end": "2025-06-30",
                                    "materiality_basis": "1% of expenses", "family": "t"}},
            {"id": "t6", "params": {"materiality": 1000.5, "period_end": "2025-06-30",
                                    "window": 3}},
            {"id": "t7", "params": {"window": 5}}]}))
        (rd / "run.json").write_text(json.dumps({"sources": [
            {"id": "dataroom", "name": "room", "path": str(room), "kind": "folder"}],
            "plan": {"playbook": "plan/r.json"}}))
        import datetime as dt
        inv = pl.DataFrame({"id": ["1", "2", "3", "4"],
                            "month": ["2025-05", "2025-05", "2025-06", "2025-06"],
                            "amount": [100.0, 50.0, 200.0, 25.5], "kind": ["INV", "CM", "INV", "INV"],
                            "start": [dt.date(2025, 1, 1), dt.date(2025, 1, 1), dt.date(2025, 3, 1),
                                      dt.date(2025, 6, 1)]})
        cache.write(rd, "inv", inv, file="inv.csv", source="dataroom", file_role="system_export",
                    header_at="A1", rows="2:5", control="amount", what="the invoices",
                    grain="one invoice",
                    columns={"id": _col("A", "invoice number"), "month": _col("B", "billing month"),
                             "amount": _col("C", "invoice amount", "usd"),
                             "kind": _col("D", "INV or CM"), "start": _col("E", "service start")})
        # a step's own parse lands in the cache through span(frame=), with its metadata
        terms = pl.DataFrame({"kind": ["INV", "CM"], "max_days": [30, 0]})
        tcols = {"kind": _col("A", "document kind"), "max_days": _col("B", "terms", "days")}
        sp = evidence.span(frame=terms, run_dir=rd, file="terms.csv", source="dataroom",
                           file_role="policy_document", header_at="A1", rows="2:3",
                           columns=tcols, id="E.t0.terms", grain="one document kind")
        tid = sp.get("cache_id")
        if not tid or tid not in {e["id"] for e in cache.manifest(rd)["files"]}:
            bad.append(f"span(frame=, run_dir=): the parse did not land in the cache: {sp}")
        if evidence.span(frame=terms, run_dir=rd, file="terms.csv", source="dataroom",
                         file_role="policy_document", header_at="A1", rows="2:3", columns=tcols,
                         grain="one document kind").get("cache_id") != tid:
            bad.append("span(frame=): the same read must land on the same cache id")

        # the catalog: in SQL, and in catalog.sql for countz-sql
        d = sql.db(rd)
        cols = d.con.execute("SELECT column_name, type, description, unit, location FROM "
                             "countz.columns WHERE table_name = 'room.inv' ORDER BY ordinal"
                             ).fetchall()
        if cols[2] != ("amount", "DECIMAL(18,2)", "invoice amount", "usd", "C") or len(cols) != 5:
            bad.append(f"countz.columns: {cols}")
        tab = d.con.execute("SELECT kind, grain, file, row_count, control_total FROM "
                            "countz.tables WHERE table_name = 'room.inv'").fetchall()
        if tab != [("source", "one invoice", "inv.csv", 4, 375.5)]:
            bad.append(f"countz.tables: {tab}")
        if "CREATE VIEW \"room\".\"inv\"" not in (rd / "catalog.sql").read_text():
            bad.append("catalog.sql does not create room.inv")

        # derived tables: the statement is kept; COMMENT ON describes; the run dir is found
        here = os.getcwd()
        os.chdir(rd / "cache")
        try:
            r = run_sql("""CREATE TABLE t1.billed AS
                           SELECT month, amount, carrying_amount(amount, start, 12,
                                  DATE '2025-06-30') AS carrying
                           FROM room.inv WHERE kind = 'INV';
                           COMMENT ON TABLE t1.billed IS 'invoices billed';
                           COMMENT ON COLUMN t1.billed.carrying IS 'carrying amount at 30 June'""")
        finally:
            os.chdir(here)
        if r != {"table": "t1.billed", "column": "carrying"}:
            bad.append(f"run_sql from inside the run dir: {r}")
        meta = sql.table_metadata(rd / "tables" / "t1" / "billed.parquet") or {}
        if "carrying_amount(amount" not in meta.get("sql", "") \
                or meta.get("reads", {}).get("tables") != ["room.inv"] \
                or meta.get("description") != "invoices billed" or meta.get("row_count") != 3:
            bad.append(f"derived table metadata: {meta}")
        got = run_sql("SELECT carrying FROM t1.billed ORDER BY month, amount", rd)["carrying"].to_list()
        if got != [50.0, 23.37, 133.33]:
            bad.append(f"carrying_amount: {got}")
        run_sql("CREATE OR REPLACE TABLE t1.billed AS SELECT month, amount, carrying_amount("
                "amount, start, 12, DATE '2025-06-30') AS carrying FROM room.inv WHERE kind = 'INV'", rd)
        if d.con.execute("SELECT description FROM countz.columns WHERE table_name = 't1.billed' "
                         "AND column_name = 'carrying'").fetchone() != ("carrying amount at 30 June",):
            bad.append("COMMENT ON does not survive CREATE OR REPLACE")
        refused("CREATE over an existing table", lambda: run_sql(
            "CREATE TABLE t1.billed AS SELECT 1 AS x", rd), "OR REPLACE")
        refused("a write to room", lambda: run_sql("CREATE TABLE room.x AS SELECT 1 AS x", rd),
                "read only")
        refused("a statement over the catalog", lambda: run_sql(
            "CREATE TABLE t1.c AS SELECT * FROM countz.tables", rd), "catalog")
        refused("a file function", lambda: run_sql("SELECT * FROM read_csv('x.csv')", rd),
                "table function")
        refused("a file read by name", lambda: run_sql("SELECT * FROM 'x.parquet'", rd), "no table")
        refused("an unknown table", lambda: run_sql("SELECT * FROM nope", rd), "no table")
        refused("a DELETE", lambda: run_sql("DELETE FROM room.inv", rd), "run_sql runs")
        if run_sql("WITH m AS (SELECT range AS i FROM range(3)) SELECT sum(i) AS s FROM m",
                   rd)["s"].to_list() != [3]:
            bad.append("a CTE over range() does not run")

        # item tables from SQL: the statement is recorded and the table reads as t0.pairs
        m = write_items(rd, "t0", "pairs", about="One row per invoice.", sql="SELECT id AS item_id, 'book' AS side, month AS "
                        "period, amount, 'usd' AS unit FROM room.inv WHERE kind = 'INV'",
                        sides=["book"], keys=["item_id"])
        if m["row_count"] != 3 or "FROM room.inv" not in (m.get("sql") or ""):
            bad.append(f"write_items(sql=): {m}")
        refused("write_items with rows and sql", lambda: write_items(
            rd, "t0", "x", [{"item_id": "a", "side": "s"}], sql="SELECT 1"), "exactly one")
        # a read of it cites the parquet: columns by name, rows by position
        sp = evidence.span("checks/t0-pairs.parquet", run_dir=rd, id="E.t9.pairs",
                           control="amount")
        if (sp["file"], sp["file_role"], sp["from_check"], sp["rows"], sp["row_count"]) != \
                ("checks/t0-pairs.parquet", "run_artifact", "t0", "1:3", 3) \
                or [c["at"] for c in sp["columns"]] != [c["name"] for c in sp["columns"]] \
                or sp["header_at"] != evidence.ARTIFACT_HEADER:
            bad.append(f"an item-table span: {sp}")
        import handoff  # noqa: PLC0415
        if handoff._item_head(rd / "checks" / "t0-pairs.parquet") != \
                (["item_id", "side", "period", "amount", "unit"], 3):
            bad.append(f"handoff's item-table head: "
                       f"{handoff._item_head(rd / 'checks' / 't0-pairs.parquet')}")
        # the brief lists a parsed table's columns inline, so a worker sees each one
        cb = "\n".join(handoff.cache_block(rd, ["inv"]))
        if "- `room.inv` — " not in cb or "Columns: id (" not in cb or "start (" not in cb:
            bad.append(f"handoff's parsed-table block: {cb}")

        # figures and populations are rows
        L = Ledger(rd, "t1")
        ps = L.populations("SELECT 'P.t1.inv' AS id, 'Invoices' AS label, count(*) AS total_n, "
                           "count(*) FILTER (kind = 'INV') AS included_n, "
                           "[{'what': 'credit memos', 'n': count(*) FILTER (kind = 'CM')}] "
                           "AS exclusions FROM room.inv")
        p = L.entries.get("P.t1.inv", {})
        if ps != ["P.t1.inv"] or (p.get("total_n"), p.get("included_n")) != (4, 3) \
                or p.get("exclusions") != [{"what": "credit memos", "n": 1}]:
            bad.append(f"populations: {p}")
        fs = L.figures("SELECT 'F.t1.billed.' || month AS id, 'Billed in ' || month AS label, "
                       "'usd' AS unit, sum(amount) AS value, 'P.t1.inv' AS population "
                       "FROM t1.billed GROUP BY month")
        e = L.entries.get("F.t1.billed.2025-06", {})
        if fs != ["F.t1.billed.2025-05", "F.t1.billed.2025-06"] or e.get("value") != 225.5 \
                or e.get("sql", {}).get("key") != {"id": "F.t1.billed.2025-06"} \
                or [i.get("citation_id") for i in e.get("inputs", [])] != ["E.t1.inv"]:
            bad.append(f"figures through a derived table to room.inv: {e}")
        if L.citations.get("E.t1.inv", {}).get("cache_id") != "inv":
            bad.append("figures: the room table is not cited with its cache id")
        L.figures("SELECT 'F.t1.share_june' AS id, 'June share' AS label, 'pct' AS unit, "
                  "fig('F.t1.billed.2025-06') / (fig('F.t1.billed.2025-05') + "
                  "fig('F.t1.billed.2025-06')) AS value")
        if [i.get("figure_id") for i in L.entries["F.t1.share_june"]["inputs"]] != \
                ["F.t1.billed.2025-06", "F.t1.billed.2025-05"]:
            bad.append(f"fig(): {L.entries['F.t1.share_june']}")
        L.figures("SELECT 'F.t1.pairs' AS id, 'Pairs' AS label, 'usd' AS unit, sum(amount) "
                  "AS value FROM t0.pairs")
        if L.entries["F.t1.pairs"]["inputs"][0]["source_type"] != "check_output" \
                or L.entries["F.t1.pairs"]["value"] != 325.5:
            bad.append(f"an item table read: {L.entries['F.t1.pairs']}")
        L.figures(f"SELECT 'F.t1.over_terms' AS id, 'On terms' AS label, 'count' AS unit, "
                  f"count(*) AS value FROM room.inv i JOIN room.\"{tid}\" t ON i.kind = t.kind "
                  f"WHERE t.max_days > 0")
        if L.entries["F.t1.over_terms"]["value"] != 3 or len(L.entries["F.t1.over_terms"]["inputs"]) != 2:
            bad.append(f"a join of two room tables: {L.entries['F.t1.over_terms']}")
        zs = L.figures("SELECT 'F.t1.cm.' || month AS id, 'Credit memos, ' || month AS label, "
                       "'usd' AS unit, coalesce(sum(amount) FILTER (kind = 'CM'), 0) AS value, "
                       "CASE WHEN coalesce(sum(amount) FILTER (kind = 'CM'), 0) = 0 "
                       "THEN 'measured_zero' END AS zero_basis, 'P.t1.inv' AS population "
                       "FROM room.inv GROUP BY month")
        if {k: L.entries[k].get("zero_basis") for k in zs} != {"F.t1.cm.2025-05": None,
                                                               "F.t1.cm.2025-06": "measured_zero"}:
            bad.append(f"zero_basis per row: {[L.entries[k] for k in zs]}")
        refused("a missing column", lambda: L.figures("SELECT 'F.t1.x' AS id, 1 AS value"), "label")
        refused("a repeated id", lambda: L.figures(
            "SELECT 'F.t1.k' AS id, 'k' AS label, 'usd' AS unit, amount AS value FROM room.inv"),
            "repeat")
        refused("an extra column", lambda: L.figures(
            "SELECT 'F.t1.k' AS id, 'k' AS label, 'usd' AS unit, 1 AS value, 2 AS memo"), "memo")
        refused("an id-like alias", lambda: L.figures(
            "SELECT 'F.t1.k' AS id, 'k' AS label, 'usd' AS unit, sum(P.amount) AS value "
            "FROM room.inv P"), "lower case")
        refused("a zero with no zero_basis", lambda: L.figures(
            "SELECT 'F.t1.k.' || kind AS id, 'k' AS label, 'usd' AS unit, 0 AS value "
            "FROM room.inv GROUP BY kind"), "zero_basis")
        if any(k.startswith("F.t1.k") for k in L.entries):
            bad.append("a refused statement left a figure behind")
        # a value typed into a recorded statement
        refused("a typed amount beside a read", lambda: L.figures(
            "SELECT 'F.t1.k' AS id, 'k' AS label, 'usd' AS unit, 1100.42 + 0 * count(*) AS value "
            "FROM room.inv"), "number(s) ['1100.42']")
        refused("a typed threshold in a table", lambda: run_sql(
            "CREATE TABLE t1.big AS SELECT * FROM room.inv WHERE amount > 250000", rd), "number(s)")
        refused("a typed rate in an item table", lambda: write_items(
            rd, "t0", "typed", sql="SELECT id AS item_id, 'book' AS side, amount * 0.1 AS "
            "amount, 'usd' AS unit FROM room.inv"), "number(s) ['0.1']")
        refused("a typed day window", lambda: run_sql(
            "CREATE TABLE t1.late AS SELECT * FROM room.inv WHERE start + INTERVAL 90 DAY > "
            "DATE '2025-06-30'", rd), "number(s) ['90']")
        refused("a typed date", lambda: run_sql(
            "CREATE TABLE t1.since AS SELECT * FROM room.inv WHERE start >= DATE '2025-03-01'", rd),
            "date(s) ['2025-03-01']")
        refused("a typed date compared as a string", lambda: run_sql(
            "CREATE TABLE t1.since AS SELECT * FROM room.inv WHERE start >= '2025-03-01'", rd),
            "date(s)")
        refused("a record id", lambda: run_sql(
            "CREATE TABLE t1.one AS SELECT * FROM room.inv WHERE kind IN ('INV', 'SO-01375')", rd),
            "record id(s) ['SO-01375']")
        refused("a typed result", lambda: write_items(
            rd, "t0", "h", sql="SELECT id AS item_id, 'book' AS side, 'held' AS result "
            "FROM room.inv"), "column(s) ['result']")
        refused("a typed status from VALUES", lambda: run_sql(
            "CREATE TABLE t1.h AS SELECT * FROM (VALUES ('a', 'pass')) v(k, status)", rd),
            "column(s) ['status']")
        refused("a typed result from a VALUES CTE", lambda: run_sql(
            "CREATE TABLE t1.h AS WITH h(k, result) AS (VALUES ('a', 'held')) SELECT * FROM h", rd),
            "column(s) ['result']")
        run_sql("CREATE TABLE t1.plain AS SELECT round(amount / 2, 2) AS half, amount / 12 AS "
                "monthly, 2025 AS yr, CASE WHEN amount > 0 THEN 'held' ELSE 'departed' END AS "
                "result, start >= DATE '2024-07-01' AS this_year FROM room.inv "
                "WHERE month IN ('2025-05', '2025-06') AND start <= DATE '2025-06-30' LIMIT 20000;"
                "COMMENT ON TABLE t1.plain IS 'One row per May or June invoice.'", rd)
        refused("a table that does not say what a row is", lambda: run_sql(
            "CREATE TABLE t1.bare AS SELECT * FROM room.inv", rd), "COMMENT ON TABLE t1.bare")
        if (rd / "tables" / "t1" / "bare.parquet").exists():
            bad.append("a refused CREATE wrote its table")
        refused("an item table that does not say what a row is", lambda: items.write_items(
            rd, "t0", "bare", [{"item_id": "a", "side": "s"}]), "give `about`")
        if [float(x) for x in run_sql("SELECT 1100.42 AS v", rd)["v"]] != [1100.42]:
            bad.append("an exploring SELECT is refused a typed number")
        L.write()
        if "F.t1.share_june" not in (rd / "catalog.sql").read_text():
            bad.append("Ledger.write did not rewrite catalog.sql with its figures")

        # lineage: the statements in order, each re-run reproduces what it made
        steps = d.con.execute("SELECT node, kind, statement, row_key, value, file FROM "
                              "lineage('F.t1.share_june')").fetchall()
        if [s[0] for s in steps] != ["room.inv", "t1.billed", "F.t1.billed.2025-05",
                                     "F.t1.billed.2025-06", "F.t1.share_june"] \
                or steps[0][5] != "inv.csv":
            bad.append(f"lineage order: {[s[:2] for s in steps]}")
        for node, kind, statement, row_key, value, _ in steps:
            if kind == "figure":
                got = d.con.execute(f"SELECT value FROM ({statement}) WHERE {row_key}").fetchone()
                if got is None or abs(float(got[0]) - float(value)) > 1e-9:
                    bad.append(f"re-performing {node}: {got} against {value}")
        rp = sql.reperform(rd, "F.t1.share_june").splitlines()
        if len(rp) != 5 or not rp[0].startswith("1. room.inv: read from inv.csv, rows 2:5") \
                or not rp[1].startswith("2. CREATE TABLE t1.billed AS SELECT") \
                or not rp[4].endswith(f"holds {L.entries['F.t1.share_june']['value']}"):
            bad.append(f"reperform: {rp}")
        if "lineage" not in str(d.con.execute("SELECT name FROM countz.functions").fetchall()):
            bad.append("countz.functions does not list lineage")
        refused("lineage() in a recorded statement", lambda: L.figures(
            "SELECT 'F.t1.n' AS id, 'n' AS label, 'count' AS unit, count(*) AS value "
            "FROM lineage('F.t1.share_june')"), "table function")

        # fig() reads a figure the open Ledger minted outside SQL: a stated cell's passthrough
        L3 = Ledger(rd, "t3")
        L3.cite({"id": "E.t3.rate", "kind": "cell", "file": "terms.csv", "source": "dataroom",
                 "file_role": "policy_document", "sheet": None, "cell": "B2",
                 "label_from": "A2 = 'INV'", "value": 0.5, "cell_kind": "literal",
                 "read_at": "2026-10-21"})
        L3.fig("F.t3.rate", "Stated rate", 0.5, "pct", "as stated at E.t3.rate (passthrough)",
               [("rate", "E.t3.rate")], disposition="as_stated")
        L3.figures("SELECT 'F.t3.half' AS id, 'Half' AS label, 'usd' AS unit, "
                   "fig('F.t1.pairs') * fig('F.t3.rate') AS value")
        if L3.entries["F.t3.half"]["value"] != 162.75:
            bad.append(f"fig() over an open Ledger's figure: {L3.entries['F.t3.half']}")
        L3.write()

        r = sql.verify(rd)
        if r["failures"] or r["tables"] != 2 or r["figures"] != 9:
            bad.append(f"verify on a clean run: {r}")

        # constants: declared from the plan, stated by a document, chosen by the step
        got = {x[0]: x[1:4] for x in sql.constant_rows(rd)}
        if got.get("materiality") != ("1000.5", None, "declared") \
                or got.get("period_end") != ("2025-06-30", "date", "declared") \
                or "window__t6" not in got or "window" in got or "family" in got:
            bad.append(f"declared constants: {got}")
        L6 = Ledger(rd, "t6")
        names = L6.constants([
            {"name": "fee_rate", "value": 0.1, "unit": "pct", "file": "policy.md",
             "source": "dataroom", "file_role": "policy_document", "locator": "paragraph 1",
             "quote": "The fee is 10% of each invoice,"},
            {"name": "fee_from", "value": "2025-03-01", "unit": "date", "file": "policy.md",
             "source": "dataroom", "file_role": "policy_document", "locator": "paragraph 1",
             "quote": "effective March 1, 2025"},
            {"name": "agreement", "value": "NP-0042", "unit": "text", "file": "policy.md",
             "source": "dataroom", "file_role": "policy_document", "locator": "paragraph 1",
             "quote": "under agreement NP-0042."},
            {"name": "grace_days", "value": 16, "unit": "days",
             "basis": "the payroll after the 15th falls within 16 days of the month end"}])
        if names != ["fee_rate", "fee_from", "agreement", "grace_days"] \
                or "E.t6.const.fee_rate" not in L6.citations:
            bad.append(f"Ledger.constants: {names}, {sorted(L6.citations)}")
        L6.figures("SELECT 'F.t6.fees' AS id, 'Fees on invoices from the policy date' AS label, "
                   "'usd' AS unit, sum(amount * const('fee_rate')) AS value FROM room.inv "
                   "WHERE start >= const_date('fee_from') AND start <= const_date('period_end')")
        e6 = L6.entries["F.t6.fees"]
        if e6["value"] != 22.55 or {"role": "const.fee_rate", "source_type": "room_file",
                                    "citation_id": "E.t6.const.fee_rate"} not in e6["inputs"] \
                or e6["sql"]["reads"]["constants"] != ["fee_rate", "fee_from", "period_end"]:
            bad.append(f"a figure over constants: {e6}")
        L6.write()
        rp6 = sql.reperform(rd, "F.t6.fees")
        if 'constant fee_rate = 0.1 pct, stated in policy.md, paragraph 1: "The fee is 10% of ' \
                'each invoice,"' not in rp6 or "constant period_end = 2025-06-30 date, declared in " \
                "plan/r.json" not in rp6:
            bad.append(f"reperform over constants: {rp6}")
        refused("a quote not in the file", lambda: L6.constants([
            {"name": "x", "value": 0.2, "unit": "pct", "file": "policy.md", "source": "dataroom",
             "file_role": "policy_document", "locator": "p1", "quote": "The fee is 20%"}]),
            "not in policy.md")
        refused("a quote that does not show the value", lambda: L6.constants([
            {"name": "x", "value": 0.2, "unit": "pct", "file": "policy.md", "source": "dataroom",
             "file_role": "policy_document", "locator": "p1",
             "quote": "The fee is 10% of each invoice,"}]), "does not show")
        refused("a declared name", lambda: L6.constants([
            {"name": "materiality", "value": 5, "unit": "usd", "basis": "x"}]), "declared by")
        refused("both a quote and a basis", lambda: L6.constants([
            {"name": "x", "value": 5, "unit": "usd", "basis": "x", "quote": "y"}]), "either")
        refused("a date read as a number", lambda: run_sql(
            "SELECT const('period_end') AS d", rd), "const_date('period_end')")
        refused("an unknown constant", lambda: run_sql("SELECT const('nope') AS d", rd),
                "holds no `nope`")
        if sql.verify(rd, "t6")["failures"]:
            bad.append(f"verify with constants: {sql.verify(rd, 't6')['failures']}")
        (room / "policy.md").write_text((room / "policy.md").read_text().replace("10%", "12%"))
        if not any("constant fee_rate" in f and "changed" in f
                   for f in sql.verify(rd, "t6")["failures"]):
            bad.append(f"verify: a changed policy file passes: {sql.verify(rd, 't6')}")
        # what was computed outside SQL fails the gate
        L5 = Ledger(rd, "t5")
        L5.population("P.t5.py", "Counted in Python", total_n=4, included_n=4)
        L5.fig("F.t5.py", "Summed in Python", 375.5, "usd", "sum(amount) over room.inv",
               [("inv", "F.t1.pairs")])
        L5.fig("F.t5.stated", "A stated rate", 0.1, "pct", "as stated at params.rate",
               [("rate", "params.rate")], disposition="as_stated")
        L5.write()
        write_items(rd, "t5", "rows", [{"item_id": "a", "side": "s", "amount": 1.0, "unit": "usd"}],
                    sides=["s"], about="One row per test item.")
        fails = sql.verify(rd, "t5")["failures"]
        if not any(f.startswith("P.t5.py") and "Ledger.populations" in f for f in fails) \
                or not any(f.startswith("F.t5.py") and "Ledger.figures" in f for f in fails) \
                or not any(f.startswith("t5.rows:") and "sql=" in f for f in fails) \
                or not any(f.startswith("F.t5.stated") and "const(" in f for f in fails) \
                or len(fails) != 4:
            bad.append(f"the outside-SQL gate: {fails}")
        for x in (rd / "workpapers" / "figures-t5.yaml", rd / "checks" / "t5-rows.parquet"):
            x.unlink()
        led = rd / "workpapers" / "figures-t1.yaml"
        doc = yaml.safe_load(led.read_text())
        for x in doc:
            if x["id"] == "F.t1.billed.2025-06":
                x["value"] = 999.0
            if x["id"] == "P.t1.inv":
                x["included_n"] = 2
        led.write_text(yaml.safe_dump(doc, sort_keys=False))
        fails = sql.verify(rd)["failures"]
        if not any("F.t1.billed.2025-06 (" in f and "999" in f for f in fails) \
                or not any(f.startswith("P.t1.inv") for f in fails):
            bad.append(f"verify: a moved figure and population are failures: {fails}")
        # a derived table whose input changed under it
        pq = rd / "tables" / "t1" / "billed.parquet"
        mm = pl.read_parquet_metadata(pq)
        pl.read_parquet(pq).head(1).write_parquet(pq, metadata={"countz": mm["countz"]})
        if not any(f.startswith("t1.billed:") for f in sql.verify(rd)["failures"]):
            bad.append("verify: a derived table that no longer matches its statement passes")
        ev = rd / "workpapers" / "evidence-t2.yaml"
        ev.write_text(yaml.safe_dump([{"id": "E.t2.raw", "kind": "span", "file": "inv.csv",
                                       "file_role": "system_export"}]))
        if not any("no cache_id" in f for f in sql.verify(rd, "t2")["failures"]):
            bad.append("verify: a span parsed outside the cache passes")

        # a table parsed from a folder of files lands in the cache and verifies
        forms = room / "forms"
        forms.mkdir()
        (forms / "a.md").write_text("fee 10\n")
        (forms / "b.md").write_text("fee 20\n")
        ff = pl.DataFrame({"file": ["a.md", "b.md"], "fee": [10.0, 20.0]})
        fs = evidence.span(frame=ff, run_dir=rd, file="forms", source="dataroom",
                           file_role="correspondence", header_at="none - one form per file",
                           rows="2 files", grain="one form",
                           columns={"file": {"at": "file name", "parse": "text",
                                             "description": "the form"},
                                    "fee": {"at": "line 1", "parse": "number",
                                            "description": "the fee", "unit": "usd"}},
                           id="E.t4.forms")
        if [x["agrees"] for x in cache.verify(rd, fs["cache_id"])] != [True]:
            bad.append("folder span: the cache does not verify")
        (forms / "b.md").write_text("fee 25\n")
        if [x["agrees"] for x in cache.verify(rd, fs["cache_id"])] != [False]:
            bad.append("folder span: a changed file in the folder still verifies")

        # a moved run: countz-sql writes the catalog anew and keeps the run's own
        moved = rd.rename(rd.with_name("moved"))
        was = (moved / "catalog.sql").read_text()
        r = subprocess.run([str(SCRIPTS / "countz-sql"), "-agent", "-init",
                            str(moved / "catalog.sql"), "-c", "SELECT count(*) AS n FROM room.inv"],
                           capture_output=True, text=True)
        if (r.returncode, r.stdout) != (0, "| n:BIGINT |\n|---|\n| 4 |\n") \
                or (moved / "catalog.orig.sql").read_text() != was \
                or str(moved.resolve()) not in (moved / "catalog.sql").read_text():
            bad.append(f"countz-sql on a moved run: {r.returncode} {r.stdout!r} {r.stderr!r}")
    if bad:
        print("sql.py self-check FAILED:")
        for b in bad:
            print(f"  - {b}")
        return 1
    print("sql.py self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
