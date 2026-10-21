#!/usr/bin/env python3
"""Self-test for scripts/sql.py (and the SQL path through figures.py and evidence.py).

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_sql.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import cache  # noqa: E402
import evidence  # noqa: E402
import sql  # noqa: E402
from figures import Ledger  # noqa: E402
from items import write_items  # noqa: E402


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
        tdp = pathlib.Path(td)
        room, rd = tdp / "room", tdp / "run"
        room.mkdir()
        rd.mkdir()
        (room / "inv.csv").write_text("id,month,amount,kind\n1,2025-05,100,INV\n2,2025-05,50,CM\n"
                                      "3,2025-06,200,INV\n4,2025-06,25.5,INV\n")
        (room / "terms.csv").write_text("kind,max_days\nINV,30\nCM,0\n")
        (rd / "run.json").write_text(json.dumps({"sources": [
            {"id": "dataroom", "name": "room", "path": str(room), "kind": "folder"}]}))
        inv = pl.DataFrame({"id": ["1", "2", "3", "4"],
                            "month": ["2025-05", "2025-05", "2025-06", "2025-06"],
                            "amount": [100.0, 50.0, 200.0, 25.5], "kind": ["INV", "CM", "INV", "INV"]})
        cols = {c: {"at": a, "parse": "as written"} for c, a in zip(inv.columns, "ABCD")}
        cache.write(rd, "inv", inv, file="inv.csv", source="dataroom", file_role="system_export",
                    header_at="A1", rows="2:5", columns=cols, control="amount")
        # a step's own parse lands in the cache through span(frame=)
        terms = pl.DataFrame({"kind": ["INV", "CM"], "max_days": [30, 0]})
        sp = evidence.span(frame=terms, run_dir=rd, file="terms.csv", source="dataroom",
                           file_role="policy_document", header_at="A1", rows="2:3",
                           columns={"kind": {"at": "A", "parse": "as written"},
                                    "max_days": {"at": "B", "parse": "integer"}},
                           id="E.t0.terms")
        tid = sp.get("cache_id")
        if not tid or tid not in {e["id"] for e in cache.manifest(rd)["files"]}:
            bad.append(f"span(frame=, run_dir=): the parse did not land in the cache: {sp}")
        again = evidence.span(frame=terms, run_dir=rd, file="terms.csv", source="dataroom",
                              file_role="policy_document", header_at="A1", rows="2:3",
                              columns={"kind": {"at": "A", "parse": "as written"},
                                       "max_days": {"at": "B", "parse": "integer"}})
        if again.get("cache_id") != tid:
            bad.append("span(frame=): the same read must land on the same cache id")
        _, sel = evidence.select(rd, "SELECT amount FROM inv WHERE kind = 'INV'", id="E.t0.inv")
        if sel.get("cache_id") != "inv":
            bad.append(f"select: the span does not name its cache id: {sel}")
        write_items(rd, "t0", "pairs", [{"item_id": "a", "side": "book", "amount": 10.0,
                                         "unit": "usd"},
                                        {"item_id": "b", "side": "book", "amount": 2.5,
                                         "unit": "usd"}],
                    sides=["book"], keys=["item_id"], citations={"book": ["E.t0.inv"]})

        db = sql.connect(rd)
        if {"inv", tid, "checks.t0-pairs"} - set(db.tables):
            bad.append(f"connect: tables {sorted(db.tables)}")
        L = Ledger(rd, "t1")
        f1 = L.fig_sql(db, "F.t1.billed", "Invoices billed", "usd",
                       "SELECT sum(amount) FROM inv WHERE kind = 'INV'")
        e1 = L.entries[f1]
        if e1["value"] != 325.5 or "SELECT sum(amount)" not in e1["expression"] \
                or e1["sql"]["text"] != e1["expression"] or e1["sql"]["key"] is not None \
                or [i["citation_id"] for i in e1["inputs"]] != ["E.t1.inv"]:
            bad.append(f"fig_sql: entry {e1}")
        if L.citations.get("E.t1.inv", {}).get("cache_id") != "inv":
            bad.append("fig_sql: the table read is not cited with its cache id")
        ms = L.figs_sql(db, "F.t1.billed.{month}", "Billed in {month}", "usd",
                        "SELECT month, sum(amount) AS value FROM inv WHERE kind = 'INV' "
                        "GROUP BY month", key="month")
        if ms != ["F.t1.billed.2025-05", "F.t1.billed.2025-06"] \
                or L.entries["F.t1.billed.2025-06"]["value"] != 225.5 \
                or L.entries["F.t1.billed.2025-06"]["sql"]["key"] != {"month": "2025-06"}:
            bad.append(f"figs_sql: {ms} {L.entries.get('F.t1.billed.2025-06')}")
        f3 = L.fig_sql(db, "F.t1.share_june", "June share of billings", "pct",
                       "SELECT fig('F.t1.billed.2025-06') / fig('F.t1.billed')")
        if abs(L.entries[f3]["value"] - 225.5 / 325.5) > 1e-9 or \
                [i.get("figure_id") for i in L.entries[f3]["inputs"]] != \
                ["F.t1.billed.2025-06", "F.t1.billed"]:
            bad.append(f"fig(): {L.entries[f3]}")
        f4 = L.fig_sql(db, "F.t1.pairs", "Item-table total", "usd",
                       'SELECT sum(amount) FROM checks."t0-pairs"')
        i4 = L.entries[f4]["inputs"][0]
        if L.entries[f4]["value"] != 12.5 or i4["source_type"] != "check_output":
            bad.append(f"artifact read: {L.entries[f4]}")
        f5 = L.fig_sql(db, "F.t1.over_terms", "Invoices on kinds with terms over 0 days", "count",
                       f'SELECT count(*) FROM inv i JOIN "{tid}" t ON i.kind = t.kind '
                       f"WHERE t.max_days > 0")
        if L.entries[f5]["value"] != 3 or len(L.entries[f5]["inputs"]) != 2:
            bad.append(f"join: {L.entries[f5]}")
        refused("file function", lambda: db.lineage("SELECT * FROM read_csv('x.csv')"),
                "table function")
        refused("unknown table", lambda: db.lineage("SELECT * FROM nope"), "no table")
        refused("unknown figure", lambda: db.lineage("SELECT fig('F.zz.nope')"), "no ledger")
        refused("not a select", lambda: db.lineage("DELETE FROM inv"), "one SELECT")
        refused("two statements", lambda: db.lineage("SELECT 1; SELECT 2"), "one statement")
        refused("id-like alias", lambda: L.fig_sql(db, "F.t1.x", "x", "usd",
                                                   "SELECT sum(P.amount) FROM inv P"), "lower case")
        refused("many rows", lambda: L.fig_sql(db, "F.t1.y", "y", "usd",
                                               "SELECT amount FROM inv"), "rows")
        refused("repeated key", lambda: L.figs_sql(db, "F.t1.k.{kind}", "k {kind}", "usd",
                                                   "SELECT kind, amount AS value FROM inv",
                                                   key="kind"), "repeats")
        if "F.t1.k.INV" in L.entries:
            bad.append("figs_sql: a refused schedule left a figure behind")
        L.write()

        r = sql.verify(rd)
        if r["failures"] or r["figures"] != 6 or "warnings" in r:
            bad.append(f"verify on a clean run: {r}")
        # a value that moved is a failure
        p = rd / "workpapers" / "figures-t1.yaml"
        doc = yaml.safe_load(p.read_text())
        for e in doc:
            if e["id"] == "F.t1.billed":
                e["value"] = 999.0
        p.write_text(yaml.safe_dump(doc, sort_keys=False))
        r = sql.verify(rd)
        if not any("F.t1.billed (" in f and "999" in f for f in r["failures"]):
            bad.append(f"verify: a moved value is not a failure: {r['failures']}")
        # a data-room span with no cache id is a failure
        ev = rd / "workpapers" / "evidence-t2.yaml"
        ev.write_text(yaml.safe_dump([{"id": "E.t2.raw", "kind": "span", "file": "inv.csv",
                                       "file_role": "system_export"}]))
        r = sql.verify(rd, "t2")
        if not any("no cache_id" in f for f in r["failures"]):
            bad.append(f"verify: a span parsed outside the cache passes: {r['failures']}")
        # fig() reads a figure the open Ledger minted outside SQL, with no hold
        db = sql.connect(rd)
        L3 = Ledger(rd, "t3")
        L3.fig("F.t3.rate", "Stated rate", 0.5, "pct", "as stated", [("rate", "params.rate")],
               disposition="as_stated")
        try:
            v = L3.fig_sql(db, "F.t3.half", "Half of the item-table total", "usd",
                           "SELECT fig('F.t1.pairs') * fig('F.t3.rate')")
            if L3.entries[v]["value"] != 6.25:
                bad.append(f"fig() over a Ledger figure: {L3.entries[v]}")
        except ValueError as exc:
            bad.append(f"fig() does not read the open Ledger's figure: {exc}")
        # a schedule with zero and non-zero rows: zero_basis lands on the zero rows only
        L3.population("P.t3.inv", "Invoices", total_n=4, included_n=4)
        try:
            zs = L3.figs_sql(db, "F.t3.cm.{month}", "Credit memos, {month}", "usd",
                             "SELECT month, coalesce(sum(amount) FILTER (kind = 'CM'), 0) AS value FROM inv "
                             "GROUP BY month", key="month", zero_basis="measured_zero",
                             population="P.t3.inv")
            zb = {k: L3.entries[k]["zero_basis"] for k in zs}
            if zb != {"F.t3.cm.2025-05": None, "F.t3.cm.2025-06": "measured_zero"}:
                bad.append(f"figs_sql zero_basis per row: {zb}")
        except ValueError as exc:
            bad.append(f"figs_sql refuses a schedule with zero and non-zero rows: {exc}")
        # an item table written after connect is read on the next statement, typed
        write_items(rd, "t3", "rows", [{"item_id": "a", "side": "s", "hours": 2, "rate": 1.5,
                                        "acct": "1350"},
                                       {"item_id": "b", "side": "s", "hours": 3, "rate": 2.0,
                                        "acct": "1360"}],
                    extensions=["hours", "rate", "acct"], sides=["s"])
        try:
            if db.value('SELECT sum(hours * rate) FROM checks."t3-rows"') != 9.0:
                bad.append("typed item table: hours * rate does not sum to 9")
            t = dict(db.con.execute('SELECT column_name, data_type FROM '
                                    'information_schema.columns WHERE table_name = '
                                    "'t3-rows'").fetchall())
            if (t.get("hours"), t.get("rate"), t.get("acct")) != ("BIGINT", "DOUBLE", "VARCHAR"):
                bad.append(f"item table types: {t}")
        except ValueError as exc:
            bad.append(f"an item table written after connect is not read: {exc}")
        # rewritten: the next statement reads the new rows
        write_items(rd, "t3", "rows", [{"item_id": "a", "side": "s", "hours": 5, "rate": 1.0,
                                        "acct": "1350"}],
                    extensions=["hours", "rate", "acct"], sides=["s"])
        if db.value('SELECT sum(hours) FROM checks."t3-rows"') != 5:
            bad.append("a rewritten item table is not re-read")
        # a CSV edited after its parquet reads as text
        import os
        import time
        csvp = rd / "checks" / "t3-rows.csv"
        time.sleep(0.01)
        csvp.write_text(csvp.read_text())
        os.utime(csvp)
        t = dict(db.con.execute('SELECT column_name, data_type FROM information_schema.columns '
                                "WHERE table_name = 't3-rows'").fetchall()) \
            if db.lineage('SELECT * FROM checks."t3-rows"') else {}
        if t.get("hours") != "VARCHAR":
            bad.append(f"a hand-edited item table is not read as text: {t}")
        L3.write()
        # a table parsed from a folder of files lands in the cache and verifies
        forms = room / "forms"
        forms.mkdir()
        (forms / "a.md").write_text("fee 10\n")
        (forms / "b.md").write_text("fee 20\n")
        ff = pl.DataFrame({"file": ["a.md", "b.md"], "fee": [10.0, 20.0]})
        try:
            fs = evidence.span(frame=ff, run_dir=rd, file="forms", source="dataroom",
                               file_role="correspondence", header_at="none - one form per file",
                               rows="2 files", columns={"file": {"at": "file name", "parse": "text"},
                                                        "fee": {"at": "line 1", "parse": "number"}},
                               id="E.t4.forms")
            if [x["agrees"] for x in cache.verify(rd, fs["cache_id"])] != [True]:
                bad.append("folder span: the cache does not verify")
            (forms / "b.md").write_text("fee 25\n")
            if [x["agrees"] for x in cache.verify(rd, fs["cache_id"])] != [False]:
                bad.append("folder span: a changed file in the folder still verifies")
        except ValueError as exc:
            bad.append(f"folder span refused: {exc}")
    if bad:
        print("sql.py self-check FAILED:")
        for b in bad:
            print(f"  - {b}")
        return 1
    print("sql.py self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
