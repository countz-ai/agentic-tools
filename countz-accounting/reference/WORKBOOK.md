# WORKBOOK — the reader's path through the workbook

`WORKBOOK_STYLE.md` is how a cell looks, applied as written on every tab. This file is
what goes where.

## 1. Three readers, three paths

- **The decider** reads Exec Summary only: the answer, what it rests on, what needs
  their eyes. They click at most once — an amount to the tab it came from.
- **The reviewer** goes Exec Summary → a check tab → its frozen band → the schedule →
  Analysis → Exceptions, and clicks any figure's id to land on its Sources row.
- **The reperformer** goes to a check tab's To reperform block, with Sources open beside
  it for the reads.

## 2. The tabs

### Tab order
- Exec Summary
- The lead tabs — the recipe's `lead:` list (`RECIPE_FORMAT.md` § The document);
  absent, the headline family's tab alone
- Basis of Preparation
- every other check tab in roster order
- Coverage, Open Items, Sources, Evidence
- Nothing hidden, nothing else.

### Tab names
`<token> <Title>` — the check's roster token as the roster spells it, one space, then a
short Title Case title: `q1 FY2021 statements`, `q6 EBITDA bridge`. At most 31
characters, no underscores, no slashes. The token leads so a cell that opens with it
links to the tab (`link_workbook.py` rule 5) and the gate can pair the tab with its
check. Run-level tabs keep their fixed names. Tab colours and gridlines:
`WORKBOOK_STYLE.md` § 4.

## 3. Tab body

No merged cells, no hidden rows or columns, no comments, no images. A long title
overflows to the right from B1; a merge breaks sort, filter, copy and every screen
reader.

### The frozen band — rows 1 to 3

Every check tab puts the following in the frozen band: a title and a quick summary of what
the tab is trying to accomplish. It orients a user on how to approach the data below. The
band is frozen at `B4`. A table header is never frozen: the primary table's header on
row 4 describes that table alone, not the tables below it.

- B1 the title, opening with the token (`q6 · Adjusted EBITDA reconciles to the ledger`).
- B2 the subtitle: entity · period set · basis · unit · tolerance. A tab covering several
  entities names the group and its count (`13 bank accounts`); the entities themselves are
  the primary table's first column, each with its own rows, subtotal and status.
- B3 the summary, at most 160 characters

### Language

Another accountant reads this workbook to re-perform the work, so it is written in the
vocabulary of a workpaper. Use standard accounting terms. Do not coin terms, and do not
carry the run's own machine vocabulary onto a tab. Voice is `DOCTRINE.md` § Voice.

A cell that states a status, a class or a verdict shows words, not the id the run computes
with. Declare the words beside the id wherever the id is declared. An id belongs in the tab's
id column, where the links resolve it, not inside a cell that reads as a sentence such as a
reason, a condition or a note. Name what was done, not which step did it.

Examples: the class `one_time_event` shows as *Non-recurring events*; the status `withheld`
as *unable to establish from the records provided*; a reason reads *the management ARR agreed
to the waterfall*, not *as a2_management_arr footed it*.

## 4. The blocks of a check tab

Below the band, in this order, each block opened by a `Section` heading in column B and
closed by one blank row. A block the check does not have is omitted — no empty headings.
The primary table has no heading; the band is its heading.

1. **The primary table** — the check's own schedule: tie schedule, reconciliation
   statement, roster, window, vouch schedule, adjustment schedule, bridge. Header on row
   4 (`BAND`), body from row 5, subtotals in `Subtotal`, the footing row in `Total`.
   The id is the first column after the margin; amounts right; the status column last.
   Every cell of the table — header, body, subtotal, total — carries the style's hairline
   on all four sides (`grid()`); Notes and To reperform rows carry none. One AutoFilter
   per tab, on this header.
2. **Analysis** — the decomposition of a failed tie or an unexplained difference: one row
   per component, `id | component | amount | disposition | evidence`, and a residual row
   whose disposition reads `unexplained`. `HeaderPlain` header.
3. **Exceptions** — one row per `X.` id: `id | item | amount | what would clear it |
   owner`. The amount is the exception's size in the schedule's unit. An `X.` id resolves
   on the tab and nowhere else, so a row whose amount a reader will want to re-perform
   names the `F.` id that measures it — in the item cell or beside it — and the reader
   follows that id to its Sources row. Without it the trail ends on the tab.
4. **Carry-forwards** — `id | what is carried | into which figures | why`.
5. **Notes** — the style's `Note` lines: the source line, the method line, the caveats
   the reader must see. One per row: the id it qualifies in B, the sentence in C.
6. **To reperform** — a `Section` heading, then a numbered list, one step per row in
   column B, `Body` style (a procedure is read, not glanced at): the read (file · sheet ·
   range), the selection rule, the arithmetic. The last thing on the tab.

**A cell holds one claim, whole.** A ruling's reason of two or three sentences is one
claim; it is never cut to a length. Prose lives in a wrapped column at least 42 wide
(§ 5) with the row's height set to fit it (§ 7 `fit_rows`), or in a cell whose row is
empty to its right, where it overflows.

## 5. Columns

A width belongs to a column letter, so every table on a tab shares one column plan:

| position | holds | width | wrap |
|---|---|---|---|
| B | id (44 on Sources) | 36 | no |
| C | description — the item, line, component, matter | 42 | yes, top-aligned |
| D … | short fields — amounts, periods, dates, words, one per letter | 14 (period 12, percent 9) | no |
| second to last | status, verdict, disposition | 12 | no |
| last | prose — reason, evidence, what would clear it, why, basis | 48 | yes, top-aligned |

A secondary table orders its columns to the plan: id, description, short fields, status,
prose last. A table with two prose columns ends with both, each 48 and wrapped.

| block | columns, in plan order |
|---|---|
| tie schedule | id · what is agreed · side A · source A · amount A · side B · source B · amount B · difference · status |
| proposed-schedule comparison | id · row · what the books carry · the figure proposed · the run's figure · difference · period proposed · period supported · verdict · reason |
| reconciliation statement | id · line · amount · classification · status · evidence |
| roster, window, vouch schedule | id · item · date · amount · matched to · result · note |
| adjustment schedule, bridge | id · line · one column per period · ruling · reason |
| Analysis | id · component · amount · disposition · evidence |
| Exceptions | id · item · amount · owner · what would clear it |
| Carry-forwards | id · what is carried · into · why |
| Notes | id · note |
| To reperform | one step per row, column B, overflowing right |

**A block that sets two records' figures side by side carries the difference between
them as its own column**, next to the two figures and before the status — the tie
schedule's shape, and the shape of any comparison of a management or third-party
schedule to the run's own work. The status is read against that column, at the coarser
grain the two records carry (DOCTRINE.md § Materiality).

A column holds one kind of number, formatted by column (style § 3): whole currency on
schedules, cents only on an item schedule that must foot to the cent, `0.0%` for shares,
`#,##0` for counts, `d mmm yyyy` for dates. No currency symbol in cells — the unit is in
the subtitle and the header. Period columns carry the period label as text (`FY2023`,
`LTM Jul 2023`), right-aligned, in the order the plan fixed, on every tab that has
periods, so a reader compares tabs column for column.

## 6. The run-level tabs

**Exec Summary** — the story of the run for the recipe's reader, and the whole of what
the decider reads. The recipe's `## Exec summary` section says who that reader is, what
they came to learn and what the story leads with. The form is the writer's — sentences,
a table copied from a check tab, a chart over such a table — chosen to carry the story. It is not a roster of checks (that
is Coverage), not the list of open items (Open Items), and not the background of the run
(Basis of Preparation). Rules:

- Band: B1 `Exec Summary · <goal, as the report names it>`; B2 entity · period set ·
  basis · unit; B3 the position in one sentence. Frozen at `B4`; the body starts on
  row 4.
- A number in a sentence is interpolated (`EVIDENCE.md` § 4).
- Every numeric cell is a copy from a check tab, in a table whose title names that tab
  and whose row labels and column headers are copied verbatim. `link_workbook.py` wires
  each amount to the cell it was copied from; `check_workbook.py` refuses one it cannot.
  A number that is not a figure (a year in a header) is written as text.
- A chart draws on the cells of such a table, on this tab.
- A check that did not run, or ran degraded, appears here only where it limits the
  answer. The full list is on Basis of Preparation.

**Basis of Preparation** — what the run stood on and how to read what it produced.
Tables, not paragraphs, in this order:

1. Sources and periods — the primary table.
2. Per check, under `HeaderPlain` headers: populations; tolerances with any loosening
   and its reason; elections with their bases and rejected sides.
3. On a plan-driven run: the recipe, the plan's approval, and each family the plan
   dropped or degraded with its reason.
4. **Procedures not performed** — one line per row: every check that did not run or
   ended blocked or failed, every check that could not establish what it set out to
   establish, and every step that ran degraded, with its reason.
5. **How to read this workbook** — the prefix table from `EVIDENCE.md` § 0, one row per
   prefix the workbook uses; then one line each for the dispositions (`measured` /
   `inferred` / `as_stated`), `passthrough`, `zero_basis`, populations (included of
   total, exclusions named), the citation form (file · sheet · range), and the one-hop
   rule: a figure id clicks to its Sources row, whose `To reperform` cell is the recipe
   and whose `root source` clicks to the Evidence row that re-selects the data. The
   reader never opens `EVIDENCE.md`; this block is their copy of it.

**Coverage** — primary table `token · title | kind | step | status | what was
examined | what was not examined, and why`, one row per rostered check, coloured per `WORKBOOK_STYLE.md` § 5.

**Open Items** — three tables under three `Section` headings — review calls, questions
for management, data requests — the first with the `BAND` header, the other two
`HeaderPlain`. Each `id | matter | size | what closes it | owner | raised by`. The last column holds the review finding's id; its header is the reader's words, not the record's field name (§ 3 Language). A `Q.`
or `D.` id the check raises is stated on that check's own tab as well, so the row's id
resolves there and the reader lands on the schedule that raised it; a row whose only link
is the check's name sends them to the top of a tab to search.

**Sources** — the ledger every figure and population id resolves on, merged from every
`workpapers/figures-*.yaml`; identical entries under one id collapse to one, and a
disagreement is a blocker for the report step, never a repair. Band: title; subtitle
naming the run and the row count; row 3 blank; header on row 4. Columns, every one
named, no spacer, these labels exactly: `id | label | value | unit | disposition |
expression | inputs | root source | To reperform | population | caveats and
carry-forwards | from check`. `inputs` and `root source` hold one id per cell, spread
across adjacent columns. `root source` is where the figure lands once every passthrough
and figure-to-figure hop is collapsed: the `E.` id(s) of the reads against the data room
(`resolve_roots.py` computes it). `To reperform` is the flattened recipe in one cell —
file · sheet · rows · columns · filter · arithmetic · expected value with its control
total; a figure that combines other figures states the combining arithmetic and points at
its input rows. A `check_output` input is presented as derived from its producing check,
never as a room read. `value` formatted by its `unit`; id column 44; `MIST` on even rows;
gridlines on.

**Evidence** — one row per `E.` id, merged from every `workpapers/evidence-*.yaml`, the
same ledger treatment. Columns: kind, file (room-relative path), source, role (a
`run_artifact` row says "derived — from <check>"), sheet, anchor (`header_at` / cell /
locator), rows, columns with their letters and `holds`, filter, row count, control
total, value basis, read date, and the note, quote or `label_from`. Header on row 4; the
source-id lines (one per source id, naming the path the run was given — text, not a
link) go below the last ledger row under a `Source roots` line.

## 7. Writing it

Every tab script imports one kit, `scripts/wbkit.py` — the style's § 9 constants and
`styles()`, and the helpers that place the band and the blocks: `band`, `header`,
`section`, `ident`, `text`, `amount`, `status`, `fit_rows`, `finish`. The script opens:

```python
import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
from wbkit import *
```

and never carries a copy of any of it: the module is the one place the kit is written,
and `check_workbook.py` GATE 4 verifies the stored workbook against the same values. Each
helper's contract is its docstring and signature in the module (`python3
${CLAUDE_PLUGIN_ROOT}/scripts/wbkit.py` self-checks it); the rules they implement are §
3 to § 5 above. `finish(ws, table_last_row, ledger=False)` sets the per-sheet settings
of the style's § 9 — the primary table's rules, row heights, the `B4` freeze, gridlines,
tab colour, the filter, print setup and the § 7 footer — after the last row is written.

## 8. Before the tab leaves staging

Write the tab into `out/.staging/`, gate it there, and rename it into place as your last
act:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_workbook.py <run_dir>/out/.staging/<tab>.xlsx --run-dir <run_dir>
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_prose.py <run_dir>/out/.staging/<tab>.xlsx --run-dir <run_dir>
```

A non-zero exit from either is the author's to fix before the rename. `--run-dir` resolves
every `F.` / `P.` / `E.` id the tab cites against the run's own `workpapers/*.yaml`
records, which gates the ids before any Sources or Evidence tab exists. An id cited but
never recorded fails here, or it reaches the deliverable, where the report step may not
repair a tab it copied. What `check_prose.py` holds the tab to is `VALIDATION.md`
§ Prose checking.

`check_workbook.py` holds the mechanical rules of this file and the style as its GATE 4
and refuses a tab at the check's own gate and again at the seal. The author's pass
covers what a parser cannot judge — the style's § 10 checklist, then:

- B1 title, B2 subtitle, B3 the summary; on a check tab row 4 the one `BAND` header;
  freeze at `B4` on every tab — the band alone, never a table header row;
- the tab name is `<token> <Title>`, at most 31 characters; tab colour per
  `WORKBOOK_STYLE.md` § 4;
- at the seal, the strip reads Exec Summary, the lead tabs, Basis of Preparation, the
  roster, the tail (§ 2);
- no merged cells, no hidden rows or columns, no `General` numeric cell; prose only in
  a description or last column, or an overflowing cell; every wrapped row sized to fit
  (§ 4, § 5);
- every table has a header in every column, the id first, the status last, a `Total`
  row where it foots, and the hairline on every side of every cell; secondary tables
  use `HeaderPlain`;
- colour appears only on status cells, a break row's variance cell, `BodyInput` figures
  and links;
- Notes then To reperform close a check tab, one line per row.

A tab that fails one of these is the author's to fix before the step record is written.
