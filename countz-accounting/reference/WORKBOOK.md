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
  absent, the headline family's tab alone. A family no check ran — left out of a scoped
  run, or dropped by the plan — has no tab and is skipped
- Basis of Preparation
- every other check tab in roster order
- Coverage, Open Items, Sources, Tables, Constants (when the run states any), Evidence
- Nothing hidden, nothing else.

A reconciliation's match tabs (check-recon § 3) follow its check's own tab, wherever
that sits: its match summary, its match schedule, its reconciling items, its match rules
(§ 6). They are that check's item detail — a lead reconciliation carries them among the
lead tabs, any other in roster order — and never stand between the Exec Summary and the
tabs its story rests on.

### Tab names
`<token> <Title>` — the check's roster token as the roster spells it, one space, then a
short title: `q1 FY2021 statements`, `q6 EBITDA bridge`; for a one-check family, the
family's title from the recipe. Where the family holds more than one check, the token is
the whole check id, its underscores as spaces, and no title follows it:
`a7 Credit balances unapplied` for `a7_credit_balances_unapplied` — `a7 Credit balances`
names no check, and `g6 stale arr Stale ARR` repeats it. At most 31 characters, no underscores, no slashes. The token leads so a cell that opens with it
links to the tab (`link_workbook.py` rule 5) and the gate can pair the tab with its
check. Run-level tabs keep their fixed names. Tab colors and gridlines:
`WORKBOOK_STYLE.md` § 4.

## 3. Tab body

No merged cells, no hidden rows or columns, no comments, no images. A long title
overflows to the right from B1; a merge breaks sort, filter, copy and every screen
reader.

### The frozen band — rows 1 to 3

Every check tab puts the following in the frozen band: a title and a quick summary of what
the tab is trying to accomplish. It orients a user on how to approach the data below. The
band is frozen at `B4`. On a tab holding one table, its header on row 4 is frozen with
the band, at `B5`. On a tab of several, no table header is frozen: the primary table's
header on row 4 describes that table alone, not the tables below it.

- B1 the title, opening with the token (`q6 · Adjusted EBITDA reconciles to the ledger`).
  On every tab, run-level and script-written tabs included, the title is what an
  accountant writes at the head of a schedule: after the name, a short phrase or one
  plain sentence saying what the tab holds or shows. It does not list the tab's columns
  or explain how to read them; the headers and B3 do that. Example — not
  `Tables · Every table the figures read: what one row is, how it was made, and what it
  reads`, but `Tables · Tables behind the figures`.
- B2 the subtitle: entity · period set · basis · unit · tolerance. The unit carries the
  primary table's currency and scale (`$ in thousands`); a column header never carries the
  scale. A tab covering several entities names the group and its count (`13 bank
  accounts`); the entities themselves are the primary table's first column, each with its
  own rows, subtotal and status.
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
`check_workbook.py` refuses a cell outside the id column that is wholly a code
(`consistent_late_payer`, `not_supported`, `phone_call: promise_to_pay`); a cell naming a
check by its id (`r5_measures`), which links to that check's tab, is navigation, not a code.

## 4. The blocks of a check tab

Below the band, in this order, each block opened by a `Section` heading in column B. A
block the check does not have is omitted — no empty headings. The primary table has no
heading; the band is its heading.

**Spacing.** One blank row between a `Section` heading and the table header under it:
Google Sheets draws a table's menus (rename, views) in the row above its header, and a
heading there is covered. The primary table is the exception — its header is row 4, under
the frozen band, where Sheets draws no menus. Two blank rows under every table, its Total
rows included, before whatever follows, so a heading reads with the table below it and
never with the one above. A block of lines (Notes, To reperform) starts on the row under
its heading. The kit writes this: `section()` returns the header's row and
`next_block(last_row)` the next heading's; `check_workbook.py` refuses either gap filled.

1. **The primary table** — the check's own schedule: tie schedule, reconciliation
   statement, roster, window, vouch schedule, adjustment schedule, bridge. Header on row
   4 (`BAND`), body from row 5, subtotals in `Subtotal`, the footing row in `Total`, each
   a formula over the rows it adds (§ 7).
   The id is the first column after the margin; amounts right; the status column last.
   Every cell of the table — header, body, subtotal, total — carries the style's hairline
   on all four sides (`grid()`); Notes and To reperform rows carry none.

**Every table is an Excel table.** A tab holding several tables cannot freeze one header
for all of them, so the band is the only frozen row and each table carries its own header
instead (a tab holding one table freezes its header with the band, § 2): `finish()` (and `link_workbook.py` again on the assembled workbook) makes every
table block an Excel table — its own range, its own filter buttons, and its header shown in
place of the column letters while the reader scrolls inside it. A block is a header row
(bold on a fill, opening after a blank row or a Section heading) and the rows under it to
the next blank row or heading; a closing Total row stays outside it, so a sort or a filter
never moves the total. A table's header labels are distinct — each names one column, and
the table takes its column names from them (`header()` refuses a repeat). No sheet-level
AutoFilter where a tab has a table.
2. **Analysis** — the decomposition of a failed tie or an unexplained difference: one row
   per component, `id | component | amount | disposition | evidence`, and a residual row
   whose disposition reads `unexplained`.
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
   range), the selection rule, the arithmetic. A table the run made is read in SQL: the
   step names `<check>.<table>` and the SELECT, never a file to open. The last thing on
   the tab.

**A schedule the recipe declares.** The recipe's `schedules` list names the tables the
deck draws from a family's tab: `from` the family, `block` the `Section` heading the table
sits under (none: the primary table), `columns` the headers it carries — the first is the
row label, one row per line it names — and `periods: all`, one more column per reported
period, headed as the plan's `params.columns`. A check of that family builds each such table
under that heading with those headers, whatever else the tab holds: a roll-forward
declared `columns: [line]` is a `Line` column (opening, additions, …, closing) beside one
column per period. `check_report.py` refuses the deck when no table on the tab carries the
declared columns, and the seal waits on the check.

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
`FMT_COUNT` for counts (written with `count()`), `mmm d, yyyy` for dates (`Sep 30, 2025`).
No currency symbol in cells — the currency is in the subtitle, and in each money column's
header when a tab holds more than one (`header(..., currency=...)`). Period columns carry the period label as text (`FY2023`,
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
- Every numeric cell is a copy from a check tab, in a table whose title carries the marker
  `from: <tab>` (the tab's full name or its token, `REPORT.md` § 2) and whose row labels and column headers are copied verbatim. `link_workbook.py` turns
  each amount into a formula reading the cell it was copied from (`='r8 Billed to
  collected'!G119`), its result cached, and links it there, so a reviewer tracing
  precedents lands on the original; `check_workbook.py` refuses one it cannot wire.
  A number that is not a figure (a year in a header) is written as text.
- A chart draws on the cells of such a table, on this tab.
- The last block is **Tabs in this workbook**: one row per tab in strip order, the tab's
  name (a check tab's cell opens with its token, so it links there) and one line on what
  a reader finds on it. With thirty tabs, a reader who does not know the roster tokens
  finds the schedule they want from here.
- A check that did not run, or ran degraded, appears here only where it limits the
  answer. The full list is on Basis of Preparation.
- A check invariant that fails, or a data-integrity exception that undermines a trend
  the story shows, is stated here beside the figure it limits — never only on the check's
  tab.
- One basis per measure. Where check tabs carry a measure on two bases (past due gross
  and net of unapplied cash), this tab names the one it uses and copies the walk between
  them.

**The match tabs** — written by `scripts/match_tabs.py`, never by hand, for every
reconciliation, whether it matched with `resolve.py`'s `resolve()` or with joins read back
through its `from_assignment()`. They report the matching as reconciliation software
does, so a reader can verify it one item at a time, and every reconciliation carries them:
`check_workbook.py` GATE 7 refuses a `recon` check's tabs without them, unless its check
tab states `No item grain:` (check-recon § 3).

- `<token> Match summary` walks from all left items (every invoice, paid or not) to each
  status, as a count and an amount: Matched, In transit (not matched, and dated close
  enough to the statement's end that its bank line falls after it; Outstanding for
  payments), Unmatched, No cash. Each status line is the schedule filtered on that status, and its words link to that status's rows. Then what each rule matched,
  and the right items matched and not in the book.
- `<token> Match schedule` has one row per left item: its label, date, amount, status, the
  rule that matched it and its match group, what it matched to, the difference a rule
  tolerated (on the group's first row only, so the column sums to the difference lines),
  and why an unmatched item is unmatched (no candidate, or more than one). It
  is sorted by status in the summary's order, so each status is one block of rows, and it
  is an Excel table filtered from its own header.
- `<token> Reconciling items` (`<token> Recon items` where the name would exceed 31
  characters) is the reconciliation, each line a figure, net and gross (its positive and
  negative items apart, adding to the net): the left items per books; less those in
  transit; less those not matched; each difference a rule tolerated; plus the right items
  not in the book; the right items per bank. Then every item not matched (the ones kept
  out with cash included), with its age at the statement's end (`res.end`).
- `<token> Match rules` (`<token> Rules` where the name would exceed 31 characters) lists the
  rules in the order they ran, each with its criteria and what it matched.

A hyperlink cannot apply a filter; the link selects the status's block instead, and
`check_workbook.py` GATE 6 refuses a line whose count or amount differs from the schedule
filtered on its status, and a reconciliation that does not foot. The tabs belong to the
check (the token leads their names) and are copied like its other tabs; a check with two
reconciliations writes two sets, each under its own token, the later set ahead of the
earlier.

**Basis of Preparation** — what the run stood on and how to read what it produced.
Tables, not paragraphs, in this order:

1. Sources and periods — the primary table.
2. Per check: populations; tolerances with any loosening
   and its reason; elections with their bases and rejected sides.
3. On a plan-driven run: the recipe, the plan's approval, and each family the plan
   dropped or degraded with its reason. On a scoped run (`run.json.plan.scope`), also
   the steps the user picked and each family left out, by its title, with *Not in this
   run's scope* as its reason.
   Then the sign-off block: `Prepared by` (Countz, with the run's date), `Reviewed by`
   and `Date reviewed`, the last two left blank for the firm's reviewer to complete.
4. **Procedures not performed** — one line per row: every family left out of the run's
   scope, every check that did not run or ended blocked or failed, every check that could not establish what it set out to
   establish, and every step that ran degraded, with its reason.
5. **How to read this workbook** — the prefix table from `EVIDENCE.md` § 0, one row per
   prefix the workbook uses; then one line each for the dispositions (`measured` /
   `inferred` / `as_stated`), `passthrough`, `zero_basis`, populations (included of
   total, exclusions named), the citation form (file · sheet · range), and the path
   down: a figure's cell clicks to its Sources row; each of its reads clicks to that
   table's row on Tables, which shows the statement that made it and its own reads; a
   table read from a file clicks to its Evidence row. The reader never opens
   `EVIDENCE.md`; this block is their copy of it.

**Coverage** — primary table `token · title | kind | step | status | what was
examined | what was not examined, and why`, one row per rostered check, colored per `WORKBOOK_STYLE.md` § 5.

**Open Items** — three tables under three `Section` headings — review calls, questions
for management, data requests. Each `id | matter | size | what closes it | owner | raised by`. Review
calls are the review findings still open to the reader — `carried_to_open_items` or
`withheld`; a finding the run fixed is the run's own history, in `RUN_SUMMARY.md`, not an
open item. Where none is open the section reads so in one line. The size is a number in
the matter's own unit, written as a number (money in the tab's currency, a count with
`count()`), and never larger than the population it concerns — a flow summed past the
balance at stake is not the size. The last column holds the review finding's id; its header is the reader's words, not the record's field name (§ 3 Language). A `Q.`
or `D.` id the check raises is stated on that check's own tab as well, so the row's id
resolves there and the reader lands on the schedule that raised it; a row whose only link
is the check's name sends them to the top of a tab to search.

**Sources, Tables, Constants, Evidence** — the ledger tabs, written by `scripts/ledger_tabs.py`
from the run's records, never by hand. They are the trail a reader follows down from a
number to the data room (`docs/REPERFORM.md`); the module's docstring states their
columns.

- **Sources**: one row per figure and population: its value, the statement that
  computed it, what that statement reads (each a link), where it lands in the data room
  (`root source`, from `resolve_roots.py`) and `To reperform`.
- **Tables**: one row per table: what one row of it is, the check that made it, its row
  count, totals and result hash, the statement that made it or the read of its file, and
  what it reads (each a link).
- **Constants**: one row per constant the statements read, with the sentence or basis it
  rests on; no tab when the run states none.
- **Evidence**: one row per read of a file, with its rows and control total, then the
  source roots.

A disagreement between two ledgers on one id is a blocker for the report step, never a
repair.

## 7. Writing it

A check writes no tab script. It writes one template, `workpapers/<check>.tpl.md`, and
`scripts/render.py` renders it to the tab, `checks/<check>.md` and
`checks/<check>-summary.md`. The template's syntax is the module's docstring: front matter
for the band, `{F.id}` in prose, and an `sql` block per table, whose rows are the table's
rows. The renderer writes through the kit, `scripts/wbkit.py` (the style's § 9 constants
and `styles()`, and the helpers that place the band and the blocks), which a run-level
tab's script imports too:

```python
import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
from wbkit import *
```

No script carries a copy of the kit, and `check_workbook.py` GATE 4 verifies the stored
workbook against the same values.

**The arithmetic is live.** A reviewer foots a schedule by its formulas and traces a
figure to where it came from by Excel's precedents, so:

- A body figure is a value: it comes from the data room, which the workbook does not
  hold, and its reperformance is its Sources row. In a template it is `cell('F.…')`, and
  the cell carries the figure's id.
- A figure you built a table on the tab to support — the rows it counts, adds or filters
  — is a formula over that table: `cell('F.…', formula := 'SUMIFS({Entries
  selected.Gross}, {Entries selected.Counterparty}, {Who or what})')`. `{Heading.Header}`
  is that column of the table under that heading; `{Header}` is this row's cell. The
  formula shows which cells the figure reads and how; it may filter on any shown column
  or on a cell of its own row. The renderer refuses one that does not reach the figure,
  and the cell links to that table instead of its Sources row. A figure no table on the
  tab supports stays a value.
- A figure of ANOTHER check is written as a copy of it. At assembly `link_workbook.py
  --run-dir` replaces it with a reference to the producing check's cell (`='r5 Position
  and DSO'!G23`), and reports a copy that disagrees with its source — the copying check's
  to fix.
- A subtotal, a total and a walk's derived line (`= …`) are rows the query marks
  (`_row`): each figure on one is a formula over the rows it adds, `Less:` lines deducted
  and a conditional sum over the verdict column where the row names a word (`_when`). The
  renderer refuses a formula that does not reach the figure, so a table missing a row or
  carrying a wrong one does not render. A figure in such a row that is not the sum of the
  rows above (a reconciliation's item count per bank) is declared stated (`_stated`).
- A recon check writes its match tabs first and passes the workbook to
  `render.render(run_dir, check, wb=wb)`.

`check_workbook.py` GATE 8 recomputes every formula from the stored values and refuses a
stale result, and on a mapped sheet refuses a subtotal, a total or a derived line typed
as a value.

## 8. Before the tab leaves staging

`render.py <run_dir> <check>` writes the tab into `out/.staging/`, gates it there, and
renames it into place; run it as your last act. The gates it runs:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_workbook.py <run_dir>/out/.staging/<tab>.xlsx --run-dir <run_dir>
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_prose.py <run_dir>/out/.staging/<tab>.xlsx --run-dir <run_dir>
uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sql.py verify <run_dir> --check <check>
```

`scripts/step_record.py`'s `place_tab(run_dir, seq)` runs all three and renames the tab into
`out/tabs/` only when all three exit 0; otherwise it raises `GateRefused` with their output
and the tab stays staged. A non-zero exit from any is the author's to fix before the
rename. `--run-dir` resolves
every `F.` / `P.` / `E.` id the tab cites against the run's own `workpapers/*.yaml`
records, which gates the ids before any Sources or Evidence tab exists. An id cited but
never recorded fails here, or it reaches the deliverable, where the report step may not
repair a tab it copied. With `--run-dir`, each tab's name must also pair with the check
(§ 2). `sql.py verify --check` refuses an id the check's ledger rows cite (a table's
statement, a figure's expression or caveats) that no tab states. What `check_prose.py`
holds the tab to is `VALIDATION.md` § Prose checking.

`check_workbook.py` holds the mechanical rules of this file and the style as its GATE 4
and refuses a tab at the check's own gate and again at the seal. The author's pass
covers what a parser cannot judge — the style's § 10 checklist, then:

- B1 title, B2 subtitle, B3 the summary; on a check tab row 4 the one `BAND` header;
  freeze at `B4` — the band alone — or at `B5` on a tab holding one table; every table an
  Excel table with distinct header labels;
- the tab name is `<token> <Title>`, at most 31 characters; tab color per
  `WORKBOOK_STYLE.md` § 4;
- at the seal, the strip reads Exec Summary, the lead tabs, Basis of Preparation, the
  roster, the tail, each check's match tabs after its own tab (§ 2);
- no merged cells, no hidden rows or columns, no `General` numeric cell; prose only in
  a description or last column, or an overflowing cell; every wrapped row sized to fit
  (§ 4, § 5);
- every table has a header in every column, the id first, the status last, a `Total`
  row where it foots, and the hairline on every side of every cell; every header `BAND`;
- color appears only on status cells, a break row's variance cell, `BodyInput` figures
  and links;
- Notes then To reperform close a check tab, one line per row.

A tab that fails one of these is the author's to fix before the step record is written.
