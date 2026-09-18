# Countz workbook style — palette, type, and application rules for xlsx financial reports

Companion to the "Find Fast, Fix Faster" slide (Paper, 2026-09-04). Same hue family, same
restraint: one accent, neutrals do the work, colour only where it carries meaning.
Ground is WHITE — the slide's bone ground does not transfer to spreadsheets (cells default
to white, tints print badly, and a tinted ground fights the gridlines).

Written to be applied by an agent. Every rule names the element it governs and the value
to set. Hex values are given without `#`; openpyxl wants `RRGGBB`, xlsxwriter wants
`#RRGGBB`.

---

## 1. Palette

Twelve colours, three groups. Contrast ratios are measured against white.

### 1a. Structure (the brand teal, three steps)

| Token      | Hex      | Role                                                                                  | Contrast |
|------------|----------|---------------------------------------------------------------------------------------|----------|
| `BAND`     | `005C53` | Fill of the ONE header band per sheet (title bar or primary table header). White text on it. | 7.9 |
| `ACCENT`   | `0F756D` | Section headings, hyperlink/id text, tab colour of deliverable tabs, the rule under the title. | 5.5 |
| `MARKER`   | `2A9D90` | Decorative only: chart series 3, sparkline, bullet dots. NEVER body text (3.3 fails at 10pt). | 3.3 |
| `TINT`     | `E1F0ED` | Fill of the headline figure cell and of a "current period" column when one must stand out. Ink text on it (12.7). | — |

### 1b. Neutrals (teal-biased greys so they sit with the accent)

| Token      | Hex      | Role                                                                   | Contrast |
|------------|----------|------------------------------------------------------------------------|----------|
| `INK`      | `1C2A2A` | All body text and computed numbers. Not pure black.                    | 14.9 |
| `SLATE`    | `566665` | Subtitle, notes, footnotes, source lines, secondary labels, ledger-tab colour. | 6.0 |
| `HAIRLINE` | `D3DAD8` | Every border: under headers, above subtotals, table rules. Never darker. | — |
| `MIST`     | `F1F5F4` | Fill of subtotal rows and of plain (non-band) header rows.             | — |
| `WHITE`    | `FFFFFF` | Ground. Text on `BAND`.                                                | — |

### 1c. Semantic (meaning only — never decoration)

| Token       | Hex text | Hex fill | Role                                                                    | Contrast (text on fill) |
|-------------|----------|----------|-------------------------------------------------------------------------|---------|
| `INPUT`     | `1F4FA3` | none     | Font colour of values transcribed from a client file (hard inputs). Computed values stay `INK`. | 7.8 on white |
| `BREAK`     | `B42318` | `FBEAE7` | Does not tie, material exception, failed check. Text always; fill on the status cell only. | 5.7 |
| `REVIEW`    | `9A5B00` | `FFF3D1` | Needs review, immaterial variance, open item.                           | 5.0 |
| `TIED`      | `1E7B3C` | `E5F3E8` | Agreed / tied / passed status cells. Text only by default; fill optional. | 4.7 |

Negative numbers are NOT red. They are in parentheses (§ 3). Red means "exception".

Chart series order: `ACCENT`, `SLATE`, `MARKER`, `REVIEW` text colour. Prior-period
comparison series: `HAIRLINE`. Never more than four series in one chart.

---

## 2. Type

**Font: Arial, every cell, every sheet.** One family. Hierarchy comes from size and
weight only.

Why Arial and not Inter (the slide face): a workbook is opened on machines we do not
control. A font the reader lacks is substituted silently and every column width shifts.
Arial is present on Windows, macOS, iOS, Google Sheets, and LibreOffice (metric-identical
Liberation Sans), has tabular digits, and is the closest ubiquitous grotesque to Inter.
If — and only if — every reader is on Microsoft 365, Aptos is the closer match to Inter;
pick one for the whole organisation and never mix.

Scale (points). No sheet uses more than four sizes; nothing below 9.

| Style       | Size | Weight      | Colour   | Use                                                        |
|-------------|------|-------------|----------|------------------------------------------------------------|
| `Title`     | 14   | bold        | `INK`    | B1: sheet title (e.g. "Cash tie-out — Dec 2025").          |
| `Subtitle`  | 10   | regular     | `SLATE`  | B2: entity · period · basis · unit ("Acme Corp · FY2025 · accrual · USD"). |
| `Section`   | 11   | bold        | `ACCENT` | A heading above each table when a sheet holds more than one. |
| `Header`    | 10   | bold        | `WHITE` on `BAND` (primary table) / `INK` on `MIST` (other tables) | Column headers. |
| `Body`      | 10   | regular     | `INK`    | Text cells, computed numbers.                              |
| `BodyInput` | 10   | regular     | `INPUT`  | Numbers and text transcribed from a client file.           |
| `Subtotal`  | 10   | bold        | `INK`    | Subtotal rows, on `MIST` fill.                             |
| `Total`     | 10   | bold        | `INK`    | Grand total row. Thin top border, double bottom border.    |
| `Note`      | 9    | italic      | `SLATE`  | Footnotes, source lines, method notes under a table.       |
| `Link`      | 10   | regular, single underline | `ACCENT` | Every hyperlink and id cell. Overrides Excel's blue/purple default. |
| `KeyFigure` | 12   | bold        | `INK` on `TINT` | The one number the sheet exists to state (headline variance, tied total). At most one per sheet. |

Letter-spacing and line-height are not controllable in xlsx; do not try.

---

## 3. Number formats

Apply by column, not by cell. Negatives in parentheses. Zero as an en dash so a
column of zeros reads as "nothing here", not as data.

| Kind                  | Format string                          | Notes                                              |
|-----------------------|----------------------------------------|----------------------------------------------------|
| Whole currency        | `#,##0;(#,##0);"–"`                    | Default for schedules and summaries.               |
| Currency with cents   | `#,##0.00;(#,##0.00);"–"`              | Detail/ledger tabs only.                           |
| Thousands             | `#,##0,;(#,##0,);"–"`                  | Trailing comma divides by 1,000 in Excel. State the unit in the header: "USD 000s". |
| Percent               | `0.0%;(0.0%);"–"`                      | One decimal. Two only for rates below 1%.          |
| Ratio / days / count  | `0.0` / `0` / `#,##0`                  | DSO, DPO, turns, counts.                           |
| Date                  | `d mmm yyyy`                           | "31 Dec 2025". Unambiguous across locales.         |
| Period header         | `mmm-yy` or text `FY2025`, `Q4 FY25`   | Right-aligned to sit over the numbers.             |
| Id / code             | text (`@`)                             | Left-aligned. Never let Excel coerce ids to numbers. |
| Currency symbol       | none in cells                          | Unit lives in the subtitle and column header.      |

---

## 4. Sheet anatomy

Every deliverable tab is built the same way, top to bottom:

```
A  = margin column, width 2, empty (keeps text off the left edge once gridlines are hidden)
B1 = Title             (row height 24)
B2 = Subtitle
row 3 = blank
row 4 = Header row     (row height 20; BAND fill + white bold on the primary table)
rows 5.. = body
  subtotal rows: MIST fill, bold, HAIRLINE top border
  total row:     bold, thin top border, DOUBLE bottom border, no fill
row after table = blank
then Notes (9 italic SLATE): source line, method line, any caveat
```

- **Freeze panes at B5** (header rows + the margin column). Never freeze deeper than 5
  rows or 2 columns — a deep freeze fills a laptop screen and blocks scrolling.
- **Gridlines OFF** on deliverable tabs (`ws.sheet_view.showGridLines = False`). ON for
  raw-data and ledger tabs where the reader scans rows.
- **One `BAND` per sheet.** The primary table's header. Secondary tables on the same
  sheet use `INK` bold on `MIST`.
- **Borders**: `HAIRLINE` on every side of every table cell — header, body, subtotal,
  total — so the table reads as a grid with gridlines off and survives print. On top of
  that: `HAIRLINE` under every header row, above every subtotal, thin top + double bottom
  on the grand total. Never an `INK` rule between cells, no outline box heavier than the
  hairline, no border on a prose or note cell. A table with no border at all is a fault:
  with gridlines off its numbers float (measured 2026-09-04).
- **No zebra striping** on schedules. Permitted only on ledger tabs longer than ~50
  rows, using `MIST` on even rows.
- **No merged cells.** For a title spanning columns, leave it in B1 and let it overflow;
  if centring is required use "center across selection". Merged cells break sort,
  filter and copy.
- **Column widths** (characters): margin 2 · id 12 · description 42 · amount 14 ·
  period 12 · percent 9 · status 12 · note 48. Wrap text on description and note
  columns; vertical-align top on wrapped columns, bottom elsewhere.
- **Alignment**: text left; numbers right; headers align with their column's content;
  period headers right; status words left. Centre nothing except a single-character flag.
- **Tab colours**: `ACCENT` for deliverable/summary tabs; `SLATE` for ledgers (Sources,
  Evidence, Population); `REVIEW` fill colour (`FFF3D1` is too pale for a tab — use the
  text colour `9A5B00`) for open-items/review tabs; none for raw data.
- **Tab order**: Summary first, then the schedules the summary's figures are drawn from, then
  the basis and the remaining schedules in the order the report cites them, ledgers last.

---

## 5. Status and conditional formatting

- A status column holds one of: `agreed`, `for review`, `difference` (or the check's own
  words — but exactly one term per state, used consistently).
- Conditional formatting on the status column only:
  - text = difference → `BREAK` text + `BREAK` fill
  - text = for review → `REVIEW` text + `REVIEW` fill
  - text = agreed     → `TIED` text, no fill
- For a `break` row, the variance cell's font goes `BREAK` red as well. Nothing else on
  the row changes colour. Never colour whole rows; never use traffic-light fills
  (pure red / yellow / green).
- Severity in a findings list uses the same three states: critical/high → `BREAK`,
  medium → `REVIEW`, low/informational → no colour. Severity is also written as a word,
  so a black-and-white print still reads.

The three states carry whichever word the status cell holds:

| the record says | style state | where the colour lands |
|---|---|---|
| `pass`, `supported`, `tied` | `TIED` | the status cell, text only |
| `warn`, `candidate`, an open item | `REVIEW` | the status cell, text and fill |
| `fail`, `unexplained`, a standing exception | `BREAK` | the status cell, text and fill; the variance cell of that row in `BREAK` text |
| `withheld`, `not_run`, a dependency not met | none — `SLATE` text | the status cell; it is an absence, not a result |

Dispositions ride the same rule: `as_stated` — a figure transcribed from a client
statement — is written in `BodyInput` blue like any hard input; `measured`, `derived`
and `inferred` stay `INK` and say their word in the disposition column. Words carry the
meaning; colour repeats it, so a black-and-white print still reads. Never red for a
negative.

**Links.** Ids are wired by `link_workbook.py`, which keeps the cell's font and sets the
style's `ACCENT` with a single underline; a linked amount takes the colour only, because
under a figure an underline means "sum above". Hand-coloured links and Excel's default
blue do not appear.

---

## 6. Charts (when a sheet carries one)

- Font Arial 9, `INK` for axis labels, `SLATE` for the axis lines; horizontal gridlines
  `HAIRLINE` only, no vertical gridlines.
- Series colours in order: `ACCENT`, `SLATE`, `MARKER`, `9A5B00`. Prior period in
  `HAIRLINE`.
- Flat fills. No 3D, no gradients, no shadows, no data labels on every point (label
  the endpoint or the total only).
- Title in `Section` style above the chart in a cell, not inside the chart object.

---

## 7. Print setup (every deliverable tab)

- Orientation: landscape for schedules wider than 8 columns, otherwise portrait.
- Fit to 1 page wide, as many tall as needed. Margins 0.5". Centre horizontally.
- Repeat rows 1:4 on every page (title, subtitle, blank, header).
- Print gridlines off. Print in black and white must still be readable — every colour
  meaning is duplicated by text (parentheses, status word, "input" column note).
- Footer: left `Confidential · Countz`, centre `&A` (sheet name), right `Page &P of &N`.
  Header: empty.

---

## 8. Forbidden (each one is a real tell of an unstyled or over-styled workbook)

- Calibri 11 or Aptos 11 left as the default (the "nobody designed this" look).
- Red font for negative numbers.
- Yellow-filled input cells; input is signalled by `INPUT` blue font, nothing else.
- Dark (`INK`) borders between cells, outline boxes heavier than the hairline, borders
  on prose cells — and the opposite fault, a table with no border at all.
- More than one `BAND` per sheet; teal fills on subtotals.
- Rainbow tab colours, a different colour per tab.
- Merged cells anywhere.
- Font size below 9, more than four sizes on a sheet, any font other than Arial.
- Emoji or symbols as status markers (✓ ✗ 🔴). Words only.
- Traffic-light row fills.

---

## 9. Implementation constants

### openpyxl

```python
from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side

BAND, ACCENT, MARKER, TINT = "005C53", "0F756D", "2A9D90", "E1F0ED"
INK, SLATE, HAIRLINE, MIST, WHITE = "1C2A2A", "566665", "D3DAD8", "F1F5F4", "FFFFFF"
INPUT = "1F4FA3"
BREAK_T, BREAK_F   = "B42318", "FBEAE7"
REVIEW_T, REVIEW_F = "9A5B00", "FFF3D1"
TIED_T, TIED_F     = "1E7B3C", "E5F3E8"

FONT = "Arial"
def font(size=10, bold=False, italic=False, color=INK, underline=None):
    return Font(name=FONT, size=size, bold=bold, italic=italic, color=color, underline=underline)

fill = lambda hex_: PatternFill("solid", fgColor=hex_)
hair = Side(style="thin", color=HAIRLINE)
thin = Side(style="thin", color=INK)
dbl  = Side(style="double", color=INK)

FMT_AMOUNT   = '#,##0;(#,##0);"–"'
FMT_CENTS    = '#,##0.00;(#,##0.00);"–"'
FMT_THOUS    = '#,##0,;(#,##0,);"–"'
FMT_PCT      = '0.0%;(0.0%);"–"'
FMT_DAYS     = '0.0'
FMT_DATE     = 'd mmm yyyy'
FMT_PERIOD   = 'mmm-yy'
FMT_TEXT     = '@'

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
    s["Title"]     = NamedStyle("cz_title",     font=font(14, bold=True))
    s["Subtitle"]  = NamedStyle("cz_subtitle",  font=font(10, color=SLATE))
    s["Section"]   = NamedStyle("cz_section",   font=font(11, bold=True, color=ACCENT))
    s["Header"]    = NamedStyle("cz_header",    font=font(10, bold=True, color=WHITE), fill=fill(BAND),
                                alignment=Alignment(vertical="center"), border=Border(bottom=hair))
    s["HeaderPlain"] = NamedStyle("cz_header_plain", font=font(10, bold=True), fill=fill(MIST),
                                alignment=Alignment(vertical="center"), border=Border(bottom=hair))
    s["Body"]      = NamedStyle("cz_body",      font=font())
    s["BodyInput"] = NamedStyle("cz_body_input", font=font(color=INPUT))
    s["Subtotal"]  = NamedStyle("cz_subtotal",  font=font(bold=True), fill=fill(MIST), border=Border(top=hair))
    s["Total"]     = NamedStyle("cz_total",     font=font(bold=True), border=Border(top=thin, bottom=dbl))
    s["Note"]      = NamedStyle("cz_note",      font=font(9, italic=True, color=SLATE))
    s["Link"]      = NamedStyle("cz_link",      font=font(color=ACCENT, underline="single"))
    s["KeyFigure"] = NamedStyle("cz_key",       font=font(12, bold=True), fill=fill(TINT))
    s["StatusBreak"]  = NamedStyle("cz_break",  font=font(color=BREAK_T),  fill=fill(BREAK_F))
    s["StatusReview"] = NamedStyle("cz_review", font=font(color=REVIEW_T), fill=fill(REVIEW_F))
    s["StatusTied"]   = NamedStyle("cz_tied",   font=font(color=TIED_T))
    return s

# per table, after its last row is written:
#   grid(ws, header_row, last_row, first_col, last_col)
# per sheet:
#   ws.sheet_view.showGridLines = False
#   ws.freeze_panes = "B5"
#   ws.column_dimensions["A"].width = 2
#   ws.row_dimensions[1].height = 24 ; ws.row_dimensions[4].height = 20
#   ws.sheet_properties.tabColor = ACCENT        # SLATE for ledgers, "9A5B00" for review tabs
#   ws.print_title_rows = "1:4"
#   ws.page_setup.orientation = "landscape" ; ws.page_setup.fitToWidth = 1 ; ws.page_setup.fitToHeight = 0
#   ws.sheet_properties.pageSetUpPr.fitToPage = True
#   ws.page_margins.left = ws.page_margins.right = ws.page_margins.top = ws.page_margins.bottom = 0.5
#   ws.oddFooter.left.text = "Confidential · Countz" ; ws.oddFooter.center.text = "&A" ; ws.oddFooter.right.text = "Page &P of &N"
#   ws.print_options.horizontalCentered = True
```

### xlsxwriter

```python
P = dict(band="#005C53", accent="#0F756D", marker="#2A9D90", tint="#E1F0ED",
         ink="#1C2A2A", slate="#566665", hairline="#D3DAD8", mist="#F1F5F4", white="#FFFFFF",
         input="#1F4FA3", break_t="#B42318", break_f="#FBEAE7",
         review_t="#9A5B00", review_f="#FFF3D1", tied_t="#1E7B3C", tied_f="#E5F3E8")
base = {"font_name": "Arial", "font_size": 10, "font_color": P["ink"]}
F = {
  "title":     wb.add_format({**base, "font_size": 14, "bold": True}),
  "subtitle":  wb.add_format({**base, "font_color": P["slate"]}),
  "section":   wb.add_format({**base, "font_size": 11, "bold": True, "font_color": P["accent"]}),
  "header":    wb.add_format({**base, "bold": True, "font_color": P["white"], "bg_color": P["band"], "bottom": 1, "bottom_color": P["hairline"], "valign": "vcenter"}),
  "header_plain": wb.add_format({**base, "bold": True, "bg_color": P["mist"], "bottom": 1, "bottom_color": P["hairline"]}),
  "body":      wb.add_format({**base}),
  "input":     wb.add_format({**base, "font_color": P["input"]}),
  "amount":    wb.add_format({**base, "num_format": '#,##0;(#,##0);"–"'}),
  "amount_in": wb.add_format({**base, "font_color": P["input"], "num_format": '#,##0;(#,##0);"–"'}),
  "pct":       wb.add_format({**base, "num_format": '0.0%;(0.0%);"–"'}),
  "subtotal":  wb.add_format({**base, "bold": True, "bg_color": P["mist"], "top": 1, "top_color": P["hairline"], "num_format": '#,##0;(#,##0);"–"'}),
  "total":     wb.add_format({**base, "bold": True, "top": 1, "top_color": P["ink"], "bottom": 6, "bottom_color": P["ink"], "num_format": '#,##0;(#,##0);"–"'}),
  "note":      wb.add_format({**base, "font_size": 9, "italic": True, "font_color": P["slate"]}),
  "link":      wb.add_format({**base, "font_color": P["accent"], "underline": 1}),
  "key":       wb.add_format({**base, "font_size": 12, "bold": True, "bg_color": P["tint"], "num_format": '#,##0;(#,##0);"–"'}),
  "s_break":   wb.add_format({**base, "font_color": P["break_t"],  "bg_color": P["break_f"]}),
  "s_review":  wb.add_format({**base, "font_color": P["review_t"], "bg_color": P["review_f"]}),
  "s_tied":    wb.add_format({**base, "font_color": P["tied_t"]}),
}
# every table format above (header, body, input, amount, pct, subtotal, total, status)
# also carries {"border": 1, "border_color": P["hairline"]}; note/section/title do not.
# per sheet: ws.hide_gridlines(2); ws.freeze_panes("B5"); ws.set_column("A:A", 2);
#   ws.set_row(0, 24); ws.set_row(3, 20); ws.set_tab_color(P["accent"]);
#   ws.repeat_rows(0, 3); ws.set_landscape(); ws.fit_to_pages(1, 0); ws.set_margins(0.5, 0.5, 0.5, 0.5);
#   ws.set_footer('&L Confidential · Countz &C &A &R Page &P of &N'); ws.center_horizontally()
```

---

## 10. Acceptance checklist for the applying agent

Open the produced workbook (or dump its XML) and confirm, per deliverable tab:

1. Every cell font is Arial; sizes used ⊆ {9, 10, 11, 12, 14}.
2. Exactly one `BAND`-filled row on the sheet.
3. Freeze pane is `B5` or shallower; gridlines hidden.
4. Column A width 2 and empty.
5. Amount columns use a three-part format with parentheses and `"–"`; no red negatives.
6. Total row has a double bottom border; subtotals have `MIST` fill; every table cell
   carries the `HAIRLINE` border on all four sides, and no prose cell does.
7. No merged cells (`ws.merged_cells.ranges` is empty).
8. Status colours appear only in the status column and, for breaks, the variance cell.
9. Hyperlinks render `ACCENT` underlined, not Excel blue.
10. Print titles `1:4`, fit-to-width 1, footer set.
