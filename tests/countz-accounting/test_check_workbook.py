#!/usr/bin/env python3
"""Self-test for scripts/check_workbook.py's cut-text rule.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_check_workbook.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import io
import pathlib
import sys
import zipfile

from openpyxl import Workbook

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_workbook  # noqa: E402


def cut_fails(texts: list[str]) -> list[str]:
    """The cut-text failures audit_design reports for a tab holding `texts` in column B."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sources"
    for i, t in enumerate(texts, 5):
        ws.cell(i, 2, t)
    buf = io.BytesIO()
    wb.save(buf)
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
        return [f for f in check_workbook.audit_design(z) if "text cut mid-word" in f]


def main() -> int:
    bad: list[str] = []
    # a whole id that opens a longer id is a key, not a cut claim (arr_analysis, 2026-10-09:
    # 28 cohort-count ids ending `.n` beside the `.nrr` ids blocked the seal)
    ids = ["F.g5.rbd.industry.financial_services.fy2022.n",
           "F.g5.rbd.industry.financial_services.fy2022.nrr"]
    if got := cut_fails(ids):
        bad.append(f"an id that opens a longer id is read as cut: {got}")
    # a sentence cut to a length beside its whole statement still fails
    whole = "The customer was billed after termination and the balance has since removed the credit."
    if not cut_fails([whole, whole[:60]]):
        bad.append("a sentence cut mid-word beside its whole statement is taken")
    # a title that repeats the check id the token spells (arr_analysis, 2026-10-16:
    # `g6 stale arr Stale ARR`); the id alone, or a one-check family's token and title, pass
    checks = [{"id": "g6_stale_arr", "params": {"family": "g6"}},
              {"id": "g6_customer_concentration", "params": {"family": "g6"}},
              {"id": "g4_cube", "params": {"family": "g4"}}]
    _, fails = check_workbook.tab_owners(checks, ["g6 stale arr Stale ARR"])
    if not any("repeats the check id" in f for f in fails):
        bad.append(f"a title repeating the check id is taken: {fails}")
    _, fails = check_workbook.tab_owners(
        checks, ["g6 Stale ARR", "g6 Customer concentration", "g4 Customer revenue cube"])
    if fails:
        bad.append(f"a tab named by its id, or by its family token and title, is refused: {fails}")
    for b in bad:
        print("FAIL", b)
    print("check_workbook: " + ("FAIL" if bad else "ok"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
