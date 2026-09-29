#!/usr/bin/env python3
"""Self-test for scripts/wbkit.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_wbkit.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from wbkit import BAND, BREAK_T, FMT_AMOUNT, FMT_COUNT, FMT_DATE, FMT_FX, FONT, TIED_T, amount, band, count, finish, header, ident, register_status, section, status, table, text  # noqa: E402


def main() -> int:
    """One tab through every helper; the styles register on the workbook and the sheet
    carries the § 9 settings."""
    import io
    from openpyxl import Workbook, load_workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "k1 Kit"
    band(ws, "k1 · the kit builds a tab", "Fixture · FY2026 · USD", "Every helper ran once.")
    header(ws, 4, ["id", "description", "amount", "status", "invoices", "euro"],
           ["id", "description", "amount", "status", "count", "amount"],
           currency={"euro": "eur"})
    ident(ws.cell(row=5, column=2), "F.k1.total")
    text(ws.cell(row=5, column=3), "A wrapped description long enough to need a second line "
                                   "inside a forty-two wide column.")
    amount(ws.cell(row=5, column=4), 1234567.89)
    status(ws.cell(row=5, column=5), "pass")
    count(ws.cell(row=5, column=6), 1204)
    amount(ws.cell(row=5, column=7), 5000.0)
    ident(ws.cell(row=6, column=2), "=1+2")             # an id opening with `=`: text, not a formula
    text(ws.cell(row=6, column=3), 12345)               # a number as a label: its digits, not blank
    register_status("matched", "tied")
    status(ws.cell(row=6, column=5), "matched")
    try:
        register_status("matched", "break")
        clash = False
    except ValueError:
        clash = True
    section(ws, 7, "Notes")
    import datetime as _dt
    last = table(ws, 9, [("id", "id"), ("item", "text"), ("balance", "amount", "eur"),
                         ("lines", "count"), ("rate", "fx_rate"), ("as of", "date"),
                         ("result", "status")],
                 [["X.k1.a", "First item", 1204.4, 3, 1.0679, _dt.date(2025, 9, 30), "pass"],
                  {"id": "X.k1.b", "item": "Second", "balance": -50.0, "lines": 1,
                   "rate": None, "as of": None, "result": "fail"}], primary=False)
    try:
        table(ws, 20, [("x", "money")], [])
        bad_kind = False
    except ValueError:
        bad_kind = True
    finish(ws, 5)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    back = load_workbook(buf)
    sheet = back["k1 Kit"]
    ok = (sheet.freeze_panes == "B4" and sheet.print_title_rows == "$1:$3"
          and sheet["B1"].font.name == FONT
          and sheet["B4"].fill.fgColor.rgb.endswith(BAND)
          and sheet["D5"].number_format == FMT_AMOUNT
          and sheet["F5"].number_format == FMT_COUNT and FMT_COUNT != FMT_AMOUNT
          and sheet["G4"].value == "euro (€)" and sheet["D4"].value == "amount"
          and sheet["E6"].font.color.rgb.endswith(TIED_T) and clash
          and FMT_DATE == "mmm d, yyyy"
          and sheet.row_dimensions[5].height is not None
          and last == 11 and bad_kind and sheet["D9"].value == "balance (€)"
          and sheet["D10"].number_format == FMT_AMOUNT and sheet["E10"].number_format == FMT_COUNT
          and sheet["F10"].number_format == FMT_FX and sheet["G10"].number_format == FMT_DATE
          and sheet["H11"].font.color.rgb.endswith(BREAK_T)
          and sheet["B11"].border.bottom.style is not None
          and (sheet["B6"].value, sheet["B6"].data_type) == ("=1+2", "s")
          and (sheet["C6"].value, sheet["C6"].data_type) == ("12345", "s")
          and sheet["B5"].value == "F.k1.total" and sheet["C5"].value.startswith("A wrapped"))
    print("wbkit: ok" if ok else "wbkit: self-check FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
