#!/usr/bin/env python3
"""Self-test for scripts/formula.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_formula.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import formula as fx  # noqa: E402


def main() -> int:
    bad: list[str] = []
    cells = {("S", "G5"): 10.0, ("S", "G6"): -3.5, ("S", "G7"): "a label", ("S", "N5"): "supported",
             ("S", "N6"): "rejected", ("T U", "E119"): 47.3, ("O'Brien", "B2"): 2.0}
    get = lambda s, c: cells.get((s, c))  # noqa: E731

    # the grammar the writers produce, and nothing wider
    cases = {"=SUM(G5:G7)": 6.5, "=SUM(G5,G6)": 6.5, "=G5+G6": 6.5, "=G5-G6": 13.5,
             "='T U'!E119": 47.3, "='O''Brien'!B2": 2.0, "=-G6+1": 4.5,
             '=SUMIFS(G5:G6,$N$5:$N$6,"supported")': 10.0,
             '=SUMIFS(G5:G6,$N$5:$N$6,"supported")+SUMIFS(G5:G6,$N$5:$N$6,"REJECTED")': 6.5,
             "=AVERAGE(G5:G6)": None, "=G5*2": None, "=VLOOKUP(G5,A:B,2)": None}
    for f, want in cases.items():
        got = fx.evaluate(f, "S", get)
        if got != want:
            bad.append(f"evaluate {f}: {got!r}, want {want!r}")
    if fx.precedents("=SUM(G5:G6)+'T U'!E119", "S") != [("S", "G5"), ("S", "G6"), ("T U", "E119")]:
        bad.append(f"precedents: {fx.precedents('=SUM(G5:G6)+' + chr(39) + 'T U' + chr(39) + '!E119', 'S')}")
    if (fx.sum_formula("G", [5, 6, 7]), fx.sum_formula("G", [7, 5]), fx.reference("a'b", "C3")) != \
            ("=SUM(G5:G7)", "=SUM(G5,G7)", "='a''b'!C3"):
        bad.append("the writers' forms")
    if fx.signed_formula("D", [5, 6, 10], [7, 8, 9]) != "=D5+D6-D7-D8-D9+D10":
        bad.append(f"signed formula: {fx.signed_formula('D', [5, 6, 10], [7, 8, 9])}")

    # footing at the precision stored, never looser: cents may round, day fractions and
    # whole numbers may not (a supported-only subtotal of 0.6154 is not the 0.6196 its
    # candidates bring the column to)
    if not fx.foots(105261519.05, 102680031.54 + -551703.28 + 3133190.79, 3,
                    [105261519.05, 102680031.54, -551703.28, 3133190.79]):
        bad.append("cents that add exactly must foot")
    if not fx.foots(10.01, 3.33 + 3.33 + 3.34 + 0.005, 4, [10.01, 3.33, 3.34]):
        bad.append("a half cent of rounding per term must foot")
    if fx.foots(0.6154252322, 0.6154252322 + 0.0009961745 + 0.0031855698, 4,
                [0.6154252322, 0.0009961745, 0.0031855698]):
        bad.append("a day fraction short by 0.004 must not foot")
    if fx.foots(8.0, 7.0, 3, [8.0, 3.0, 4.0]):
        bad.append("whole numbers foot exactly or not at all")

    # results chained through cells and sheets, then cached into the saved file
    from openpyxl import Workbook, load_workbook
    wb = Workbook()
    a = wb.active
    a.title = "a1 Base"
    a["B5"], a["B6"], a["B7"] = 2.0, 3.0, "=SUM(B5:B6)"
    b = wb.create_sheet("b1 Walk")
    b["C5"], b["C6"], b["C7"] = "='a1 Base'!B7", 4.0, "=C5+C6"
    b["C8"] = "=AVERAGE(C5:C6)"                         # outside the grammar: left out
    got = fx.compute_results(wb)
    if got != {"a1 Base": {"B7": 5.0}, "b1 Walk": {"C5": 5.0, "C7": 9.0}}:
        bad.append(f"compute_results: {got}")
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "w.xlsx"
        wb.save(p)
        if load_workbook(p, data_only=True)["b1 Walk"]["C7"].value is not None:
            bad.append("openpyxl stores a result: the premise of cache_results is gone")
        n = fx.cache_results(p, got)
        back = load_workbook(p, data_only=True)
        if n != 3 or back["b1 Walk"]["C7"].value != 9.0 or back["a1 Base"]["B7"].value != 5.0:
            bad.append(f"cache_results: {n} written, C7 reads {back['b1 Walk']['C7'].value}")
        if load_workbook(p)["b1 Walk"]["C7"].value != "=C5+C6":
            bad.append("cache_results must keep the formula")
        # a formula outside the grammar keeps the result Excel cached, by the fallback
        if fx.compute_results(load_workbook(p), fallback=back).get("b1 Walk", {}).get("C7") != 9.0:
            bad.append("compute_results falls back on a cached result")

    if bad:
        for b_ in bad:
            print(f"FAIL {b_}")
        print("formula: FAIL")
        return 1
    print("formula: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
