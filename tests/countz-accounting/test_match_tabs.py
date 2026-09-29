#!/usr/bin/env python3
"""Self-test for scripts/match_tabs.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_match_tabs.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import polars as pl

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from match_tabs import match_tabs  # noqa: E402


def main() -> int:
    import json
    import tempfile
    import zipfile

    from openpyxl import Workbook, load_workbook

    import check_workbook
    import link_workbook
    from figures import Ledger
    from resolve import Pass, from_assignment, resolve, rules
    bad = []
    D = dt.date(2024, 3, 1)
    left = pl.DataFrame([("i1", "c1", D, 100.37), ("i2", "c1", D, 250.13), ("i3", "c2", D, 75.25),
                         ("i4", "c3", D + dt.timedelta(days=9), 81.10),
                         ("i5", "c4", D + dt.timedelta(days=40), 12.34)],
                        orient="row", schema=["id", "entity", "date", "value"])
    right = pl.DataFrame([("d1", "A", D, 350.50), ("d2", "A", D, 75.25),
                          ("d3", "A", D + dt.timedelta(days=9), 81.10),
                          ("d4", "B", D + dt.timedelta(days=20), 9.99)],
                         orient="row", schema=["id", "entity", "date", "value"])
    res = resolve(left, right, rules(window=(0, 2)))
    with tempfile.TemporaryDirectory() as tmp:
        run = pathlib.Path(tmp)
        (run / "workpapers").mkdir()
        L = Ledger(run, "m1", fresh=True)
        L.cite({"id": "E.m1.left", "kind": "span", "file": "l.xlsx", "source": "l",
                "file_role": "system_export", "sheet": "S", "header_at": "A1", "rows": "2:6",
                "columns": [], "filter": "none - full sheet consumed", "row_count": 5,
                "control_total": {"column": "v", "value": 519.19}})
        L.population("P.m1.left", "left items", 6, 6, citations=["E.m1.left"])
        L.population("P.m1.right", "right items", 4, 4, citations=["E.m1.left"])
        wb = Workbook()
        wb.active.title = "m1 Reconciliation"
        out = match_tabs(wb, res, left, right, check="m1", token="m1", ledger=L,
                         subtitle="Fixture · March 2024 · USD", inputs=[("left", "E.m1.left")],
                         population="P.m1.left", right_population="P.m1.right",
                         others=pl.DataFrame({"id": ["i9"], "value": [0.0], "reason": ["open"]}),
                         left_label=pl.DataFrame({"id": ["i1"], "label": ["Customer One"]}))
        L.write()
        path = run / "tab.xlsx"
        wb.save(path)
        wbb = load_workbook(path)
        if wbb.sheetnames[:4] != [out["summary"], out["schedule"], out["reconciling"], out["rules"]]:
            bad.append(f"the four tabs lead the file: {wbb.sheetnames}")
        sch = wbb[out["schedule"]]
        states = [sch.cell(r, 6).value for r in range(5, 11)]
        if states != ["Matched"] * 4 + ["In transit", "No cash"]:
            bad.append(f"the schedule is sorted by status: {states}")
        with zipfile.ZipFile(path) as z:
            if fails := check_workbook.audit_match(z, assembled=False):
                bad.append(f"the match gate refuses the builder's own tabs: {fails[:3]}")
            if design := [f for f in check_workbook.audit_design(z) if out["summary"] in f or out["schedule"] in f]:
                bad.append(f"the design gate refuses the tabs: {design[:3]}")
        rec = load_workbook(path)
        rec[out["reconciling"]]["F5"].value = rec[out["reconciling"]]["F5"].value + 1   # and a gross
        rec.save(run / "gross.xlsx")                                                   # that is not the net
        with zipfile.ZipFile(run / "gross.xlsx") as z:
            if not any("positive and negative" in f for f in check_workbook.audit_match(z, assembled=False)):
                bad.append("a line whose gross is not its net passes the gate")
        ws = wbb[out["summary"]]
        ws["D6"].value = ws["D6"].value + 1                    # a tampered line is refused
        wbb.save(path)
        with zipfile.ZipFile(path) as z:
            if not check_workbook.audit_match(z, assembled=False):
                bad.append("a summary line that is not the filter passes the gate")
        wbl = load_workbook(path)
        targets = link_workbook.match_targets(wbl)
        if targets.get((out["summary"], "C6")) != (out["schedule"], "B5:K8") or \
                targets.get((out["summary"], "C7")) != (out["schedule"], "B9:K9"):
            bad.append(f"each line links to its rows: {targets}")

        # a match built with joins gets the same tabs, and they say where it came from
        asg = res.items.select("side", "id", "status", "group", "pass", reason=pl.lit(None, pl.Utf8))
        fa = from_assignment(left, right, asg, [Pass(r, "as resolve() ran it") for r in res.by_rule["rule"]],
                             transit=2)
        L2 = Ledger(run, "m2", fresh=True)
        L2.population("P.m2.left", "left items", 5, 5, citations=["E.m1.left"])
        wb2 = Workbook()
        wb2.active.title = "m2 Reconciliation"
        out2 = match_tabs(wb2, fa, left, right, check="m2", token="m2", ledger=L2,
                          subtitle="Fixture · March 2024 · USD", inputs=[("left", "E.m1.left")],
                          population="P.m2.left")
        wb2.save(run / "src.xlsx")
        with zipfile.ZipFile(run / "src.xlsx") as z:
            if fails := check_workbook.audit_match(z, assembled=False):
                bad.append(f"the match gate refuses tabs from from_assignment(): {fails[:3]}")
        said = " ".join(str(c.value) for row in load_workbook(run / "src.xlsx")[out2["summary"]].iter_rows()
                        for c in row if c.value)
        if "the passes on m2 Match rules" not in said or "resolve.py run on" in said:
            bad.append("the summary's To reperform names the passes of a join-built match")

        # GATE 7: every reconciliation carries its match tabs
        (run / "run.json").write_text(json.dumps({"checks": [
            {"id": "m1", "kind": "recon"}, {"id": "m2", "kind": "recon"}, {"id": "t1", "kind": "tieout"}]}))

        def gate7(name, sheets, notes=None, drop=()):
            w = load_workbook(run / "src.xlsx")
            for t in [t for t in w.sheetnames if t not in sheets] + list(drop):
                del w[t]
            if notes:
                w[w.sheetnames[-1]]["B20"] = notes
            w.save(run / f"{name}.xlsx")
            return check_workbook.audit(run / f"{name}.xlsx", run_dir=run)["recon"]
        every = load_workbook(run / "src.xlsx").sheetnames
        for name, sheets, notes, drop, refused, what in (
                ("m2", every, None, (), False, "a reconciliation with its match tabs"),
                ("m2", ["m2 Reconciliation"], None, (), True, "a reconciliation with no match tabs"),
                ("m2", every, None, (out2["reconciling"], out2["rules"]), True, "a reconciliation with half a set"),
                ("m2", ["m2 Reconciliation"], "No item grain: the statement holds its closing balance alone.",
                 (), False, "a reconciliation that states a side with no item grain"),
                ("t1", ["m2 Reconciliation"], None, (), False, "a tie-out, which matches nothing")):
            if bool(gate7(name, sheets, notes, drop)) != refused:
                bad.append(f"GATE 7 {'passes' if refused else 'refuses'} {what}")
        with zipfile.ZipFile(run / "src.xlsx") as z:
            if check_workbook.audit_recon(z, "m2", None):
                bad.append("GATE 7 holds a tab gated without the run's roster")
        seal = load_workbook(run / "src.xlsx")
        seal.create_sheet("Exec Summary", 0)
        seal.save(run / "workbook.xlsx")
        with zipfile.ZipFile(run / "workbook.xlsx") as z:
            if check_workbook.audit_recon(z, "workbook", run):
                bad.append("GATE 7 refuses a sealed reconciliation with its match tabs")
        for t in (out2["summary"], out2["schedule"], out2["reconciling"], out2["rules"]):
            del seal[t]
        seal.save(run / "workbook.xlsx")
        with zipfile.ZipFile(run / "workbook.xlsx") as z:
            if [f.split(":")[0] for f in check_workbook.audit_recon(z, "workbook", run)] != ["m2"]:
                bad.append("GATE 7 passes a sealed reconciliation whose match tabs were dropped")
    for b in bad:
        print("FAIL", b)
    print("match_tabs.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
