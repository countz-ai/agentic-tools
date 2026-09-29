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

Dates and currency symbols come from scripts/style.py (US conventions: a date cell reads
`Sep 30, 2025`). A money column's header names its currency when the tab is not in one
currency throughout - `header(..., currency="eur")` or `currency={"Balance": "eur"}` -
since an amount cell carries no symbol. A count column is written with `count()` in
`FMT_COUNT`, a format no money column uses, so a reader of the stored file (the deck
builder scaling money columns) tells a count from an amount by its format, not its header.
A recipe's own status words take a style with `register_status("matched", "tied")`.
"""
from __future__ import annotations

import pathlib
import sys

from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style as _style  # noqa: E402  sibling: date forms and currency symbols

__all__ = [
    # palette (WORKBOOK_STYLE.md § 1)
    "BAND", "ACCENT", "MARKER", "TINT", "INK", "SLATE", "HAIRLINE", "MIST", "WHITE",
    "INPUT", "BREAK_T", "BREAK_F", "REVIEW_T", "REVIEW_F", "TIED_T", "TIED_F",
    # type and rules
    "FONT", "font", "fill", "hair", "thin", "dbl",
    # number formats (WORKBOOK_STYLE.md § 6)
    "FMT_AMOUNT", "FMT_CENTS", "FMT_THOUS", "FMT_PCT", "FMT_DAYS", "FMT_DATE",
    "FMT_PERIOD", "FMT_TEXT", "FMT_COUNT", "FMT_FX", "FMT_RATE",
    # styles and helpers
    "grid", "styles", "S", "STATUS", "STATUS_KINDS", "register_status", "WIDTH", "WRAP",
    "band", "header", "section", "ident", "text", "amount", "count", "status", "table", "KINDS", "fit_rows",
    "finish", "excel_tables", "table_blocks", "get_column_letter", "Alignment",
]

# --- WORKBOOK_STYLE.md § 9 ------------------------------------------------------------
BAND, ACCENT, MARKER, TINT = "0A5F6A", "0A5F6A", "16203A", "E6EFF0"
INK, SLATE, HAIRLINE, MIST, WHITE = "1C2130", "5E616A", "D8D8D9", "EDEBE3", "FFFFFF"
INPUT = "1F4FA3"
BREAK_T, BREAK_F = "A33A2E", "EDEBE3"
REVIEW_T, REVIEW_F = "8A5A00", "EDEBE3"
TIED_T, TIED_F = "0A5F6A", "EDEBE3"

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
# A count: whole, grouped, padded right so it aligns with a parenthesized negative. Its
# own string - never FMT_AMOUNT - so the stored format tells a count from money.
FMT_COUNT = '#,##0_);(#,##0);"–"_)'
FMT_FX = '0.0000'
FMT_RATE = '0.00%'
FMT_DATE = _style.FMT_DATE_CELL                  # "Sep 30, 2025"
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
STATUS_KINDS = {"tied": "StatusTied", "review": "StatusReview", "break": "StatusBreak",
                "note": "Note"}
WIDTH = {"margin": 2, "id": 36, "id_ledger": 44, "description": 42, "amount": 14,
         "count": 10, "period": 12, "percent": 9, "status": 12, "note": 48}
RIGHT = ("amount", "count", "period", "percent")


def register_status(word: str, kind: str) -> None:
    """A recipe's own status word (`matched`, `exception`, `in_transit`) and the style it
    reads in: `tied`, `review`, `break` or `note`. An unregistered word reads as a Note."""
    if kind not in STATUS_KINDS:
        raise ValueError(f"status kind {kind!r}: one of {', '.join(STATUS_KINDS)}")
    have = STATUS.get(word)
    if have and have != STATUS_KINDS[kind]:
        raise ValueError(f"status {word!r} is already {have}; one word, one style")
    STATUS[word] = STATUS_KINDS[kind]
WRAP = Alignment(wrap_text=True, vertical="top")


def band(ws, title, subtitle, summary=None):
    ws.column_dimensions["A"].width = WIDTH["margin"]
    ws["B1"].value, ws["B1"].style = title, S["Title"]
    ws["B2"].value, ws["B2"].style = subtitle, S["Subtitle"]
    ws.row_dimensions[1].height, ws.row_dimensions[4].height = 24, 20
    if summary:
        ws["B3"].value, ws["B3"].style = summary, S["Body"]


def header(ws, row, labels, widths, primary=True, currency=None):
    """The table header. `currency` names the currency of the money (`amount`) columns:
    one code for all of them (`"eur"`), or `{label: code}` per column; each such header
    reads `Balance (€)`. Omitted, the band's subtitle states the tab's one currency.
    Labels are distinct within the table: each names one column to the reader, and an
    Excel table (`excel_tables`) takes its column names from them."""
    seen = [str(v).strip().casefold() for v in labels]
    if dup := sorted({v for v in seen if seen.count(v) > 1}):
        raise ValueError(f"header row {row}: labels repeat {dup} — name what each column "
                         f"holds (`Amount, invoices` / `Amount, bank lines`)")
    for i, (label, width) in enumerate(zip(labels, widths), start=2):
        unit = currency.get(label) if isinstance(currency, dict) else \
            (currency if width == "amount" else None)
        if unit:
            sym = _style.symbol(unit).strip()
            if sym not in str(label):
                label = f"{label} ({sym})"
        c = ws.cell(row=row, column=i, value=label)
        c.style = S["Header"] if primary else S["HeaderPlain"]
        ws.column_dimensions[get_column_letter(i)].width = WIDTH[width]
        if width in RIGHT:
            c.alignment = Alignment(horizontal="right", vertical="center")


def section(ws, row, text_):
    ws.cell(row=row, column=2, value=text_).style = S["Section"]


def ident(cell, id_):
    cell.value, cell.style = id_, S["Body"]     # style first: it resets number_format
    if isinstance(id_, str):
        cell.data_type = "s"                    # an id opening with `=` is not a formula
    cell.number_format = FMT_TEXT


def text(cell, v, style="Body"):
    if v is not None and not isinstance(v, str):
        v = str(v)                              # a string cell stores a number as blank
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


def count(cell, value, style=None):
    """A count of things: FMT_COUNT, never a money format."""
    if value is not None and float(value) != round(float(value)):
        raise ValueError(f"a count of {value} is not a whole number")
    cell.value = value
    cell.style = S[style] if style else S["Body"]
    cell.number_format = FMT_COUNT


def status(cell, word):
    cell.value = word
    cell.style = S[STATUS[word]] if word in STATUS else S["Note"]


# A table column's kind: (WIDTH key, how a value is written).
KINDS = {"id": "id", "text": "description", "note": "note", "amount": "amount",
         "cents": "amount", "count": "count", "pct": "percent", "rate": "percent",
         "fx_rate": "amount", "days": "count", "date": "period", "period": "period",
         "status": "status"}


def table(ws, row, columns, rows, primary=True):
    """A whole table: the header on `row`, one row per member of `rows`, every cell ruled
    (`grid`). `columns` is `[(label, kind)]` or `[(label, kind, currency)]` — `kind` one of
    `KINDS`, a currency code on an `amount`/`cents` column heading it `Balance (€)`. A row
    is a sequence in column order or a dict keyed by label. Each value is written by its
    column's kind: `id` → `ident`, `amount` → `amount` (whole units), `cents` → two
    decimals, `count` → `count`, `pct` / `rate` / `fx_rate` / `days` / `date` their
    formats, `status` → `status`, `text` / `note` → `text`. Returns the last row written."""
    cols = []
    for c in columns:
        label, kind, cur = (tuple(c) + (None,))[:3]
        if kind not in KINDS:
            raise ValueError(f"column {label!r}: kind {kind!r}, one of {', '.join(KINDS)}")
        if cur and kind not in ("amount", "cents"):
            raise ValueError(f"column {label!r}: a currency is stated on an amount column only")
        cols.append((label, kind, cur))
    header(ws, row, [c[0] for c in cols], [KINDS[c[1]] for c in cols], primary=primary,
           currency={c[0]: c[2] for c in cols if c[2]})
    r = row
    for member in rows:
        r += 1
        vals = [member.get(c[0]) for c in cols] if isinstance(member, dict) else list(member)
        if len(vals) != len(cols):
            raise ValueError(f"row {r}: {len(vals)} values for {len(cols)} columns")
        for i, ((label, kind, _), v) in enumerate(zip(cols, vals), start=2):
            cell = ws.cell(row=r, column=i)
            if v is None:
                cell.style = S["Body"]
            elif kind == "id":
                ident(cell, v)
            elif kind in ("text", "note"):
                text(cell, v)
            elif kind == "status":
                status(cell, v)
            elif kind == "count":
                count(cell, v)
            else:
                fmt = {"amount": FMT_AMOUNT, "cents": FMT_CENTS, "pct": FMT_PCT,
                       "rate": FMT_RATE, "fx_rate": FMT_FX, "days": FMT_DAYS,
                       "date": FMT_DATE, "period": FMT_PERIOD}[kind]
                amount(cell, v, fmt=fmt)
            if kind in ("amount", "cents", "count", "pct", "rate", "fx_rate", "days"):
                cell.alignment = Alignment(horizontal="right", vertical="top")
    grid(ws, row, r, 2, 1 + len(cols))
    return r


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


def _rgb(cell) -> str:
    f = cell.fill
    if f is None or f.fill_type != "solid" or f.fgColor is None:
        return ""
    return str(f.fgColor.rgb or "")[-6:].upper() if f.fgColor.type == "rgb" else "theme"


def _is_header_cell(cell) -> bool:
    """A table header cell as stored: a bold label on a solid fill (BAND or MIST, or an
    earlier palette's). Read from the resolved font and fill, not the named style, so a
    tab copied cell by cell into the assembled workbook reads as the tab file it came from."""
    return (isinstance(cell.value, str) and bool(cell.value.strip())
            and bool(cell.font and cell.font.b) and bool(_rgb(cell)))


def table_blocks(ws, first_row=4):
    """Every table on the tab as `(header_row, first_col, last_col, last_body_row)`.

    A header is a run of two or more header cells from column B that opens a block: on
    row 4, after a blank row or a Section heading, or anywhere as a row of labels alone —
    a table stacked under another with no blank row between still starts afresh. A
    subtotal carries the same fill but sits under body rows beside its figures, so it
    never opens one. The block runs to the first blank row, Section heading or next
    header; a closing Total row (double bottom rule) stays outside it, so sorting or
    filtering the table never moves the total."""
    def empty(r, c1, c2):
        return all(ws.cell(row=r, column=c).value in (None, "") for c in range(c1, c2 + 1))

    def heading(r, c2):                         # a Section heading opens the next block
        b = ws.cell(row=r, column=2)
        return (bool(b.font and b.font.b) and not _rgb(b) and b.value not in (None, "")
                and empty(r, 3, max(c2, 3)))

    def total(r, c1, c2):
        return any((b := ws.cell(row=r, column=c).border) is not None and b.bottom is not None
                   and b.bottom.style == "double" for c in range(c1, c2 + 1))

    def span(r):                                # the header's last column, or None
        if not _is_header_cell(ws.cell(row=r, column=2)):
            return None
        c2 = 2
        while c2 < ws.max_column and _is_header_cell(ws.cell(row=r, column=c2 + 1)):
            c2 += 1
        return c2 if c2 > 2 else None

    def labels_only(r):
        return all(not isinstance(ws.cell(row=r, column=c).value, (int, float))
                   for c in range(2, ws.max_column + 1))

    def opens(r):
        c2 = span(r)
        if c2 and (r == first_row or empty(r - 1, 3, c2) or labels_only(r)):
            return c2
        return None

    blocks, r, last_row = [], first_row, ws.max_row
    while r <= last_row:
        c2 = opens(r)
        if not c2:
            r += 1
            continue
        end = r
        while (end < last_row and not empty(end + 1, 2, c2) and not heading(end + 1, c2)
               and not opens(end + 1)):
            end += 1
        body_end = end
        while body_end > r and total(body_end, 2, c2):
            body_end -= 1
        if body_end > r:
            blocks.append((r, 2, c2, body_end))
        r = end + 1
    return blocks


def _table_name(title: str, n: int, taken: set) -> str:
    import re
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", title).strip("_") or "Tab"
    name = f"T_{stem}_{n}"[:250]
    while name.casefold() in taken:
        n += 1
        name = f"T_{stem}_{n}"[:250]
    taken.add(name.casefold())
    return name


def excel_tables(ws, taken=None) -> list[str]:
    """Make every table on the tab an Excel table: its own range, its own filter
    buttons, and its header shown in place of the column letters while the reader
    scrolls inside it. A tab holding several tables cannot freeze one header for all
    of them (the band is the only frozen row); a table object carries its own.

    Replaces the tab's existing tables and its sheet-level AutoFilter, which must not
    overlap a table. `taken` is the workbook's set of table names (case-folded) — table
    names are unique across a workbook. A block whose header is not a set of distinct
    labels is left as plain cells: Excel repairs, rather than opens, a table whose
    header cells disagree with its column names. Returns the names written."""
    from openpyxl.worksheet.table import Table, TableColumn
    from openpyxl.worksheet.filters import AutoFilter
    taken = set() if taken is None else taken
    for name in list(ws.tables):
        del ws.tables[name]
    written = []
    for n, (hr, c1, c2, last) in enumerate(table_blocks(ws), start=1):
        labels = [ws.cell(row=hr, column=c).value for c in range(c1, c2 + 1)]
        if len({str(v).strip().casefold() for v in labels}) != len(labels):
            continue
        ref = f"{get_column_letter(c1)}{hr}:{get_column_letter(c2)}{last}"
        t = Table(displayName=_table_name(ws.title, n, taken), ref=ref,
                  autoFilter=AutoFilter(ref=ref))
        t.tableColumns = [TableColumn(id=i, name=str(v)) for i, v in enumerate(labels, start=1)]
        t.tableStyleInfo = None                 # the kit's cell styles are the look
        ws.add_table(t)
        written.append(t.displayName)
    if written:
        ws.auto_filter = AutoFilter()
    return written


def finish(ws, table_last_row, ledger=False, header_row=4, freeze="B4"):
    """The per-sheet settings of WORKBOOK_STYLE.md § 9, after the last row is written."""
    grid(ws, header_row, table_last_row, 2, ws.max_column)   # the primary table's rules
    fit_rows(ws)
    ws.freeze_panes = freeze
    ws.sheet_view.showGridLines = ledger
    ws.sheet_properties.tabColor = SLATE if ledger else ACCENT
    if not excel_tables(ws):                    # no table object: the sheet filter on the header
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
