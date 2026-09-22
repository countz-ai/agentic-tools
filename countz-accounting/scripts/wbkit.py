#!/usr/bin/env python3
"""The workbook kit: WORKBOOK_STYLE.md § 9's constants and `styles()`, and WORKBOOK.md
§ 7's helpers, as one importable module.

Every tab script imports this module rather than carrying the code. A tab script opens:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from wbkit import *

and writes its tab with `band`, `header`, `section`, `ident`, `text`, `amount`, `status`
and `finish`. The style constants, formats and `styles()` are the ones `check_workbook.py`
GATE 4 verifies on the stored workbook; the two documents describe them and this file is
the one place they are written. A copy of any of it in a tab script is drift the gate
reports after the fact — measured 2026-09-22 on one revenue run: eighteen scripts carried
the kit, each typed from the document.

Run with no arguments to self-check: builds one tab with every helper and exits 0.
"""
from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side
from openpyxl.utils import get_column_letter

__all__ = [
    # palette (WORKBOOK_STYLE.md § 1)
    "BAND", "ACCENT", "MARKER", "TINT", "INK", "SLATE", "HAIRLINE", "MIST", "WHITE",
    "INPUT", "BREAK_T", "BREAK_F", "REVIEW_T", "REVIEW_F", "TIED_T", "TIED_F",
    # type and rules
    "FONT", "font", "fill", "hair", "thin", "dbl",
    # number formats (WORKBOOK_STYLE.md § 6)
    "FMT_AMOUNT", "FMT_CENTS", "FMT_THOUS", "FMT_PCT", "FMT_DAYS", "FMT_DATE",
    "FMT_PERIOD", "FMT_TEXT",
    # styles and helpers
    "grid", "styles", "S", "STATUS", "WIDTH", "WRAP",
    "band", "header", "section", "ident", "text", "amount", "status", "fit_rows",
    "finish", "get_column_letter", "Alignment",
]

# --- WORKBOOK_STYLE.md § 9 ------------------------------------------------------------
BAND, ACCENT, MARKER, TINT = "005C53", "0F756D", "2A9D90", "E1F0ED"
INK, SLATE, HAIRLINE, MIST, WHITE = "1C2A2A", "566665", "D3DAD8", "F1F5F4", "FFFFFF"
INPUT = "1F4FA3"
BREAK_T, BREAK_F = "B42318", "FBEAE7"
REVIEW_T, REVIEW_F = "9A5B00", "FFF3D1"
TIED_T, TIED_F = "1E7B3C", "E5F3E8"

FONT = "Arial"


def font(size=10, bold=False, italic=False, color=INK, underline=None):
    return Font(name=FONT, size=size, bold=bold, italic=italic, color=color, underline=underline)


fill = lambda hex_: PatternFill("solid", fgColor=hex_)  # noqa: E731
hair = Side(style="thin", color=HAIRLINE)
thin = Side(style="thin", color=INK)
dbl = Side(style="double", color=INK)

FMT_AMOUNT = '#,##0;(#,##0);"–"'
FMT_CENTS = '#,##0.00;(#,##0.00);"–"'
FMT_THOUS = '#,##0,;(#,##0,);"–"'
FMT_PCT = '0.0%;(0.0%);"–"'
FMT_DAYS = '0.0'
FMT_DATE = 'd mmm yyyy'
FMT_PERIOD = 'mmm-yy'
FMT_TEXT = '@'


def grid(ws, first_row, last_row, first_col, last_col):
    """The hairline on every side of every table cell. A side a style already rules
    (the header's bottom, the total's top and double bottom) keeps its rule."""
    for r in range(first_row, last_row + 1):
        for c in range(first_col, last_col + 1):
            cell = ws.cell(row=r, column=c)
            b = cell.border
            keep = lambda side: side if (side is not None and side.style) else hair  # noqa: E731
            cell.border = Border(left=hair, right=hair, top=keep(b.top), bottom=keep(b.bottom))


def styles():
    s = {}
    s["Title"] = NamedStyle("cz_title", font=font(14, bold=True))
    s["Subtitle"] = NamedStyle("cz_subtitle", font=font(10, color=SLATE))
    s["Section"] = NamedStyle("cz_section", font=font(11, bold=True, color=ACCENT))
    s["Header"] = NamedStyle("cz_header", font=font(10, bold=True, color=WHITE), fill=fill(BAND),
                             alignment=Alignment(vertical="center"), border=Border(bottom=hair))
    s["HeaderPlain"] = NamedStyle("cz_header_plain", font=font(10, bold=True), fill=fill(MIST),
                                  alignment=Alignment(vertical="center"), border=Border(bottom=hair))
    s["Body"] = NamedStyle("cz_body", font=font())
    s["BodyInput"] = NamedStyle("cz_body_input", font=font(color=INPUT))
    s["Subtotal"] = NamedStyle("cz_subtotal", font=font(bold=True), fill=fill(MIST), border=Border(top=hair))
    s["Total"] = NamedStyle("cz_total", font=font(bold=True), border=Border(top=thin, bottom=dbl))
    s["Note"] = NamedStyle("cz_note", font=font(9, italic=True, color=SLATE))
    s["Link"] = NamedStyle("cz_link", font=font(color=ACCENT, underline="single"))
    s["KeyFigure"] = NamedStyle("cz_key", font=font(12, bold=True), fill=fill(TINT))
    s["StatusBreak"] = NamedStyle("cz_break", font=font(color=BREAK_T), fill=fill(BREAK_F))
    s["StatusReview"] = NamedStyle("cz_review", font=font(color=REVIEW_T), fill=fill(REVIEW_F))
    s["StatusTied"] = NamedStyle("cz_tied", font=font(color=TIED_T))
    return s


# --- WORKBOOK.md § 7 -------------------------------------------------------------------
S = styles()
STATUS = {"pass": "StatusTied", "supported": "StatusTied", "tied": "StatusTied",
          "warn": "StatusReview", "candidate": "StatusReview",
          "fail": "StatusBreak", "unexplained": "StatusBreak"}
WIDTH = {"margin": 2, "id": 36, "id_ledger": 44, "description": 42, "amount": 14,
         "period": 12, "percent": 9, "status": 12, "note": 48}
WRAP = Alignment(wrap_text=True, vertical="top")


def band(ws, title, subtitle, summary=None):
    ws.column_dimensions["A"].width = WIDTH["margin"]
    ws["B1"].value, ws["B1"].style = title, S["Title"]
    ws["B2"].value, ws["B2"].style = subtitle, S["Subtitle"]
    ws.row_dimensions[1].height, ws.row_dimensions[4].height = 24, 20
    if summary:
        ws["B3"].value, ws["B3"].style = summary, S["Body"]


def header(ws, row, labels, widths, primary=True):
    for i, (label, width) in enumerate(zip(labels, widths), start=2):
        c = ws.cell(row=row, column=i, value=label)
        c.style = S["Header"] if primary else S["HeaderPlain"]
        ws.column_dimensions[get_column_letter(i)].width = WIDTH[width]
        if width in ("amount", "period", "percent"):
            c.alignment = Alignment(horizontal="right", vertical="center")


def section(ws, row, text_):
    ws.cell(row=row, column=2, value=text_).style = S["Section"]


def ident(cell, id_):
    cell.value, cell.style = id_, S["Body"]     # style first: it resets number_format
    cell.number_format = FMT_TEXT


def text(cell, v, style="Body"):
    cell.value, cell.style = v, S[style]
    cell.data_type = "s"                        # a label opening with `=` is not a formula
    cell.number_format = FMT_TEXT
    ws = cell.parent
    if (ws.column_dimensions[cell.column_letter].width or 0) >= WIDTH["description"]:
        cell.alignment = WRAP                   # description and note columns wrap


def amount(cell, value, fmt=None, hard_input=False, style=None):
    cell.value = value
    cell.style = S[style] if style else (S["BodyInput"] if hard_input else S["Body"])
    cell.number_format = fmt or FMT_AMOUNT


def status(cell, word):
    cell.value = word
    cell.style = S[STATUS[word]] if word in STATUS else S["Note"]


def fit_rows(ws, first_row=5):
    """An explicit height on every row holding a wrapped cell: the viewer does not fit
    rows on open. Mirrors check_workbook.py `lines_needed` — change both."""
    for row in ws.iter_rows(min_row=first_row):
        lines = 1
        for c in row:
            if isinstance(c.value, str) and c.alignment.wrap_text:
                width = ws.column_dimensions[c.column_letter].width or 8
                lines = max(lines, -(-len(c.value) // int(width * 1.1)))
        if lines > 1:
            ws.row_dimensions[row[0].row].height = 13 * lines + 2


def finish(ws, table_last_row, ledger=False, header_row=4, freeze="B4"):
    """The per-sheet settings of WORKBOOK_STYLE.md § 9, after the last row is written."""
    grid(ws, header_row, table_last_row, 2, ws.max_column)   # the primary table's rules
    fit_rows(ws)
    ws.freeze_panes = freeze
    ws.sheet_view.showGridLines = ledger
    ws.sheet_properties.tabColor = SLATE if ledger else ACCENT
    ws.auto_filter.ref = f"B{header_row}:{get_column_letter(ws.max_column)}{table_last_row}"
    ws.print_title_rows = "1:3"                                # the band; never a table header
    ws.page_setup.orientation, ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = "landscape", 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    for side in ("left", "right", "top", "bottom"):
        setattr(ws.page_margins, side, 0.5)
    ws.print_options.horizontalCentered = True
    ws.oddFooter.left.text = "Confidential · Countz"           # WORKBOOK_STYLE.md § 7
    ws.oddFooter.center.text = "&A"
    ws.oddFooter.right.text = "Page &P of &N"


def _selfcheck() -> int:
    """One tab through every helper; the styles register on the workbook and the sheet
    carries the § 9 settings."""
    import io
    from openpyxl import Workbook, load_workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "k1 Kit"
    band(ws, "k1 · the kit builds a tab", "Fixture · FY2026 · USD", "Every helper ran once.")
    header(ws, 4, ["id", "description", "amount", "status"],
           ["id", "description", "amount", "status"])
    ident(ws.cell(row=5, column=2), "F.k1.total")
    text(ws.cell(row=5, column=3), "A wrapped description long enough to need a second line "
                                   "inside a forty-two wide column.")
    amount(ws.cell(row=5, column=4), 1234567.89)
    status(ws.cell(row=5, column=5), "pass")
    section(ws, 7, "Notes")
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
          and sheet.row_dimensions[5].height is not None)
    print("wbkit: ok" if ok else "wbkit: self-check FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
