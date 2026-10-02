# Countz workbook style — palette, type, and application rules for xlsx financial reports

Colors are the Countz design system's: one teal for identity and action, ink and
navy-tinted greys for everything else, color only where it carries meaning. The ground is
white, not the design system's sea foam: cells default to white, and tints print badly.

Written to be applied by an agent. Every rule names the element it governs and the value
to set. Hex values are given without `#`; openpyxl wants `RRGGBB`, xlsxwriter wants
`#RRGGBB`.

---

## 1. Palette

Each token names the design-system token it matches. Contrast ratios are measured against white
unless stated.

### 1a. Structure

| Token      | Hex      | Design token | Role                                                                                  | Contrast |
|------------|----------|--------------|---------------------------------------------------------------------------------------|----------|
| `BAND`     | `0A5F6A` | `--color-brand` | Fill of the ONE header band per sheet (title bar or primary table header). White text on it. | 7.35 |
| `ACCENT`   | `0A5F6A` | `--color-action` | Section headings, hyperlink/id text, tab color of deliverable tabs, the rule under the title. | 7.35 |
| `MARKER`   | `16203A` | `--color-navy` | Chart series 3 only. Never text, never a fill beside `BAND` or `ACCENT` (2.20 against teal). | — |
| `TINT`     | `E6EFF0` | `--color-surface-accent` | Fill of the headline figure cell and of a "current period" column when one must stand out. Ink text on it (13.7). | — |

### 1b. Neutrals (ink and navy tinted over the ground)

| Token      | Hex      | Design token | Role                                                                   | Contrast |
|------------|----------|--------------|------------------------------------------------------------------------|----------|
| `INK`      | `1C2130` | `--color-text` | All body text and computed numbers. Not pure black.                  | 16.0 |
| `SLATE`    | `5E616A` | `--color-text-muted` | Subtitle, notes, footnotes, source lines, secondary labels, ledger-tab color. | 6.2 |
| `HAIRLINE` | `D8D8D9` | `--color-border` | Every border: under headers, above subtotals, table rules. Never darker. | — |
| `MIST`     | `EDEBE3` | `--color-surface-inset` | Fill of subtotal rows.                                        | — |
| `WHITE`    | `FFFFFF` | `--color-surface` | Ground. Text on `BAND`.                                            | — |

### 1c. Semantic (meaning only, never decoration)

Status text sits on the inset surface, as the design system's badges do.

| Token       | Hex text | Hex fill | Design token | Role                                                                    | Contrast (text on fill) |
|-------------|----------|----------|--------------|-------------------------------------------------------------------------|---------|
| `INPUT`     | `1F4FA3` | none     | none (workbook convention) | Font color of values transcribed from a client file (hard inputs). Computed values stay `INK`. | 7.8 on white |
| `BREAK`     | `A33A2E` | `EDEBE3` | `--color-danger` | Does not tie, material exception, failed check. Text always; fill on the status cell only. | 5.5 |
| `REVIEW`    | `8A5A00` | `EDEBE3` | `--color-warning` | Needs review, immaterial variance, open item.                           | 5.0 |
| `TIED`      | `0A5F6A` | `EDEBE3` | `--color-success` | Agreed / tied / passed status cells. Text only by default; fill optional. | 6.2 |

Negative numbers are NOT red. They are in parentheses (§ 3). Red means "exception".

Chart series order: `ACCENT`, `SLATE`, `MARKER`, `REVIEW` text color. Prior-period
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
pick one for the whole organization and never mix.

Scale (points). No sheet uses more than four sizes; nothing below 9.

| Style       | Size | Weight      | Color   | Use                                                        |
|-------------|------|-------------|----------|------------------------------------------------------------|
| `Title`     | 14   | bold        | `INK`    | B1: sheet title (e.g. "Cash tie-out — Dec 2025").          |
| `Subtitle`  | 10   | regular     | `SLATE`  | B2: entity · period · basis · unit ("Acme Corp · FY2025 · accrual · USD"). |
| `Section`   | 11   | bold        | `ACCENT` | A heading above each table when a sheet holds more than one. |
| `Header`    | 10   | bold        | `WHITE` on `BAND`, every table | Column headers. |
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
| Match-tab amount, 0-decimal currency | `#,##0;(#,##0);"–"`   | `match_tabs()` shows every amount at the currency's minor units: JPY, KRW. |
| Match-tab amount, 3-decimal currency | `#,##0.000;(#,##0.000);"–"` | KWD, BHD, OMR. A 2-decimal currency's match tabs use the cents string. |
| Thousands             | `#,##0,;(#,##0,);"–"`                  | Trailing comma divides by 1,000 in Excel. State the scale once, in the table's title — the band subtitle's unit for the primary table, the `Section` heading for any other ("Aging by customer ($ in thousands)") — never in a column header, as the deck does (`REPORT.md` § 4). |
| Percent               | `0.0%;(0.0%);"–"`                      | One decimal.                                       |
| Rate                  | `0.00%` (`FMT_RATE`)                   | An interest, discount or growth rate.              |
| FX rate               | `0.0000` (`FMT_FX`)                    | Units of one currency per another.                 |
| Ratio / days          | `0.0`                                  | DSO, DPO, turns.                                   |
| Count                 | `#,##0_);(#,##0);"–"_)` (`FMT_COUNT`)  | Counts of things, written with `count()`. Its own string, never the whole-currency one, so a reader of the stored file (the deck scaling money columns) tells a count from money by the format. |
| Date                  | `mmm d, yyyy` (`FMT_DATE`)             | "Sep 30, 2025". US order, month spelled, so never ambiguous. From `scripts/style.py`. |
| Period header         | `mmm-yy` or text `FY2025`, `Q4 FY25`   | Right-aligned to sit over the numbers.             |
| Id / code             | text (`@`)                             | Left-aligned. Never let Excel coerce ids to numbers. |
| Currency symbol       | none in cells                          | The currency lives in the subtitle; a tab holding more than one currency names each money column's in its header — `header(..., currency={"Balance": "eur"})` writes `Balance (€)`. |

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
two rows after the table (its Total included) = blank
then each further block: Section heading, one blank row, its table
  (a block of lines — Notes, To reperform — starts right under its heading)
```

- **Freeze panes at B4** (title, subtitle, summary + the margin column). Never freeze a
  table header row: the primary table's header on row 4 is not the header of the tables
  below it, and a header pinned over a table it does not describe misleads the reader.
  Never freeze deeper than 3 rows or 2 columns — a deep freeze fills a laptop screen and
  blocks scrolling. Each table carries its own header instead, as an Excel table: its
  filter buttons, and its header in place of the column letters while the reader scrolls
  inside it (`WORKBOOK.md` § 4).
- **Gridlines OFF** on deliverable tabs (`ws.sheet_view.showGridLines = False`). ON for
  raw-data and ledger tabs where the reader scans rows.
- **Every table header is `BAND`.** The primary table on row 4 and every table below
  it read alike, so the reader knows a header by its color wherever the table sits.
  `BAND` fills a header row and nothing else.
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
  count 10 · period 12 · percent 9 · status 12 · note 48. Wrap text on description and note
  columns; vertical-align top on wrapped columns, bottom elsewhere.
- **Alignment**: text left; numbers right; headers align with their column's content;
  period headers right; status words left. Center nothing except a single-character flag.
- **Tab colors**: `ACCENT` for deliverable/summary tabs; `SLATE` for ledgers (Sources,
  Evidence, Population); `REVIEW` text color (`8A5A00`) for open-items/review tabs; none for raw data.
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
  the row changes color. Never color whole rows; never use traffic-light fills
  (pure red / yellow / green).
- Severity in a findings list uses the same three states: critical/high → `BREAK`,
  medium → `REVIEW`, low/informational → no color. Severity is also written as a word,
  so a black-and-white print still reads.

The three states carry whichever word the status cell holds:

| the record says | style state | where the color lands |
|---|---|---|
| `pass`, `supported`, `tied` | `TIED` | the status cell, text only |
| `warn`, `candidate`, an open item | `REVIEW` | the status cell, text and fill |
| `fail`, `unexplained`, a standing exception | `BREAK` | the status cell, text and fill; the variance cell of that row in `BREAK` text |
| `withheld`, `not_run`, a dependency not met | none — `SLATE` text | the status cell; it is an absence, not a result |

A recipe's own status word (`matched`, `in_transit`, `exception`) takes one of these
states once, before the tab is written: `register_status("matched", "tied")` (kinds
`tied`, `review`, `break`, `note`). An unregistered word reads as a note.

Dispositions ride the same rule: `as_stated` — a figure transcribed from a client
statement — is written in `BodyInput` blue like any hard input; `measured`, `derived`
and `inferred` stay `INK` and say their word in the disposition column. Words carry the
meaning; color repeats it, so a black-and-white print still reads. Never red for a
negative.

**Links.** Ids are wired by `link_workbook.py`, which keeps the cell's font and sets the
style's `ACCENT` with a single underline; a linked amount takes the color only, because
under a figure an underline means "sum above". Hand-colored links and Excel's default
blue do not appear.

---

## 6. Charts (when a sheet carries one)

- Font Arial 9, `INK` for axis labels, `SLATE` for the axis lines; horizontal gridlines
  `HAIRLINE` only, no vertical gridlines.
- Series colors in order: `ACCENT`, `SLATE`, `MARKER`, `8A5A00`. Prior period in
  `HAIRLINE`.
- Flat fills. No 3D, no gradients, no shadows, no data labels on every point (label
  the endpoint or the total only).
- Title in `Section` style above the chart in a cell, not inside the chart object.

---

## 7. Print setup (every deliverable tab)

- Orientation: landscape for schedules wider than 8 columns, otherwise portrait.
- Fit to 1 page wide, as many tall as needed. Margins 0.5". Center horizontally.
- Repeat rows 1:3 on every page (title, subtitle, summary). Never a table header row:
  the row-4 header belongs to the primary table alone, and repeated on a page that
  holds a later table it labels columns it does not describe. Each table's header
  prints once, where the table starts.
- Print gridlines off. Print in black and white must still be readable — every color
  meaning is duplicated by text (parentheses, status word, "input" column note).
- Footer: left `Confidential · Countz`, center `&A` (sheet name), right `Page &P of &N`.
  Header: empty.

---

## 8. Forbidden (each one is a real tell of an unstyled or over-styled workbook)

- Calibri 11 or Aptos 11 left as the default (the "nobody designed this" look).
- Red font for negative numbers.
- Yellow-filled input cells; input is signalled by `INPUT` blue font, nothing else.
- Dark (`INK`) borders between cells, outline boxes heavier than the hairline, borders
  on prose cells — and the opposite fault, a table with no border at all.
- `BAND` on anything but a table header — teal fills on subtotals or totals; a table
  header in any other fill.
- Rainbow tab colors, a different color per tab.
- Merged cells anywhere.
- Font size below 9, more than four sizes on a sheet, any font other than Arial.
- Emoji or symbols as status markers (✓ ✗ 🔴). Words only.
- Traffic-light row fills.

---

## 9. Implementation constants

### openpyxl

The constants below, `font()`, `fill`, the three `Side`s, the number formats and
`styles()` are code in `scripts/wbkit.py`, which every tab script imports
(`WORKBOOK.md` § 7). They are not copied into a script: the module is the one place the
palette and the named styles are written, and `check_workbook.py` verifies the stored
workbook against the same values. The names, for reading a tab script:

- palette: `BAND`, `ACCENT`, `MARKER`, `TINT`, `INK`, `SLATE`, `HAIRLINE`, `MIST`,
  `WHITE`, `INPUT`, `BREAK_T`/`BREAK_F`, `REVIEW_T`/`REVIEW_F`, `TIED_T`/`TIED_F` — the
  hex values of § 1;
- type: `FONT` (Arial), `font(size, bold, italic, color, underline)`;
- rules: `hair` (thin `HAIRLINE`), `thin` (thin `INK`), `dbl` (double `INK`); `grid(ws,
  first_row, last_row, first_col, last_col)` puts the hairline on every side of every
  table cell and keeps a side a style already rules;
- formats: `FMT_AMOUNT`, `FMT_CENTS`, `FMT_THOUS`, `FMT_PCT`, `FMT_RATE`, `FMT_FX`,
  `FMT_DAYS`, `FMT_COUNT`, `FMT_DATE`, `FMT_PERIOD`, `FMT_TEXT` — § 3;
- helpers beyond placement: `count(cell, n)` (a count in `FMT_COUNT`),
  `header(..., currency=)` (a money column's currency in its header),
  `section(ws, row, text)` (returns the header row, one blank row below) and
  `next_block(last_row)` (the next heading's row, two blank rows below a table),
  `register_status(word, kind)` (a recipe's status word and its state);
- `styles()`: the named styles `Title`, `Subtitle`, `Section`, `Header` (the `BAND`),
  `HeaderPlain` (the same look, kept for scripts that name it), `Body`, `BodyInput`, `Subtotal`, `Total`, `Note`, `Link`,
  `KeyFigure`, `StatusBreak`, `StatusReview`, `StatusTied`, registered as `cz_*` on the
  workbook; `S = styles()` at import.

Per sheet, `finish()` in the same module sets: gridlines off (on for a ledger), freeze
panes `B4`, column A width 2, row 1 height 24 and row 4 height 20, the tab color
(`ACCENT`; `SLATE` for a ledger), an Excel table per table block in `TableStyleLight1` with
stripes off (the cell styles are the look; a table naming no style is dropped by Google
Sheets on import), print titles `1:3`, landscape fit to one page wide, 0.5
margins, horizontal centring, and the § 7 footer.

### xlsxwriter

```python
P = dict(band="#0A5F6A", accent="#0A5F6A", marker="#16203A", tint="#E6EFF0",
         ink="#1C2130", slate="#5E616A", hairline="#D8D8D9", mist="#EDEBE3", white="#FFFFFF",
         input="#1F4FA3", break_t="#A33A2E", break_f="#EDEBE3",
         review_t="#8A5A00", review_f="#EDEBE3", tied_t="#0A5F6A", tied_f="#EDEBE3")
base = {"font_name": "Arial", "font_size": 10, "font_color": P["ink"]}
F = {
  "title":     wb.add_format({**base, "font_size": 14, "bold": True}),
  "subtitle":  wb.add_format({**base, "font_color": P["slate"]}),
  "section":   wb.add_format({**base, "font_size": 11, "bold": True, "font_color": P["accent"]}),
  "header":    wb.add_format({**base, "bold": True, "font_color": P["white"], "bg_color": P["band"], "bottom": 1, "bottom_color": P["hairline"], "valign": "vcenter"}),
  "header_plain": wb.add_format({**base, "bold": True, "font_color": P["white"], "bg_color": P["band"], "bottom": 1, "bottom_color": P["hairline"]}),
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
# per table: ws.add_table(hdr_row, 1, last_body_row, last_col,
#   {"columns": [{"header": h} for h in labels], "style": "Table Style Light 1",
#    "banded_rows": False})   # its own filter; Total row outside; a named style, or Sheets drops it
# per sheet: ws.hide_gridlines(2); ws.freeze_panes("B4"); ws.set_column("A:A", 2);
#   ws.set_row(0, 24); ws.set_row(3, 20); ws.set_tab_color(P["accent"]);
#   ws.repeat_rows(0, 2); ws.set_landscape(); ws.fit_to_pages(1, 0); ws.set_margins(0.5, 0.5, 0.5, 0.5);
#   ws.set_footer('&L Confidential · Countz &C &A &R Page &P of &N'); ws.center_horizontally()
```

---

## 10. Acceptance checklist for the applying agent

Open the produced workbook (or dump its XML) and confirm, per deliverable tab:

1. Every cell font is Arial; sizes used ⊆ {9, 10, 11, 12, 14}.
2. Every table header row is `BAND`-filled, row 4 among them, and `BAND` fills nothing else.
3. Freeze pane is `B4` — no table header row frozen; gridlines hidden; every table an
   Excel table (`ws.tables`), none overlapping a sheet AutoFilter.
4. Column A width 2 and empty.
5. Amount columns use a three-part format with parentheses and `"–"`; no red negatives.
6. Total row has a double bottom border; subtotals have `MIST` fill; every table cell
   carries the `HAIRLINE` border on all four sides, and no prose cell does.
7. No merged cells (`ws.merged_cells.ranges` is empty).
8. Status colors appear only in the status column and, for breaks, the variance cell.
9. Hyperlinks render `ACCENT` underlined, not Excel blue.
10. Print titles `1:3` — no table header row repeated; fit-to-width 1, footer set.
