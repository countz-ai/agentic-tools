# EVIDENCE — how a number is cited and recorded

Every figure in the deliverable traces to a cell in a file the user gave us. This file
defines the records that carry that trace. Read it before writing any step that produces
a number.

## 0. The id namespace

Every object a run creates carries an id with a one- or two-letter prefix. Adding an
object kind means adding a row to this table first; `check-plugin.py` refuses a prefix
used anywhere in the plugin that the table does not declare. The reader's copy of the
table is the workbook: check-report reproduces it on Basis of Preparation (WORKBOOK.md
§ 6) and `scripts/link_workbook.py` links every cited id to the cell where it resolves
(check-report SKILL § 1).

| prefix | object | lives in |
|---|---|---|
| `E.` | **evidence** — one recorded read of one file | `workpapers/evidence-<suffix>.yaml` (suffix = `profile-<source id>` for a profile, the check id for a check); merged into the workbook's **Evidence** tab |
| `F.` | **figure** — one number that may appear in the deliverable | `workpapers/figures-<check>.yaml` |
| `P.` | **population** — a named row set a figure is measured over | `workpapers/figures-<check>.yaml` |
| `T.` | **tie** — one asserted agreement between sides, and its result | `checks/<check>.md` |
| `RI.` | **reconciling item** — one classified, quantified component of a difference | `checks/<check>.md` |
| `S.` | **source election** — which of two disagreeing sources was trusted, and why | `checks/<check>.md` |
| `AJ.` | **adjustment** — one adjustment to a reported figure, minted by the recipe family that rules on it: rung or cause, subtype, origin, signed per-period amounts, ruling, evidence | `checks/<check>.md`, rolled up in the recipe's headline walk |
| `H.` | **hypothesis** — one candidate lever stated in falsifiable form, with its null, test, population, power and result, reported whether supported or refuted; minted by the recipe family that tests it | `checks/<check>.md`, rolled up in the recipe's hypothesis register |
| `LK.` | **leak** — one quantity of receivable or revenue billed and not collected, attributed to one named mechanism, with its dollars, days and verdict; minted by the recipe family that establishes it | `checks/<check>.md`, rolled up in the recipe's headline walk |
| `X.` | **exception** — one item that failed a check's assertion, with what would clear it and who owns that | `checks/<check>.md`, rolled up in the report's exception schedule |
| `C.` | **review finding** | the review step's record |
| `D.` | **data request** — an open item: something missing from the files | the report's open items |
| `Q.` | **question for management** — an open item only they can answer | the report's open items |

In the workbook, `F.` and `P.` ids resolve on the **Sources** tab and `E.` ids on the
**Evidence** tab; every other prefix resolves on the tab of the check that states it.

**The suffix** names what the object is (`E.gl_detail.fy2026`, `RI.deposits_in_transit`),
never a serial number. A sequence number is used only where the object has no natural
name, e.g. a review finding or an election. The same quantity earned in two checks is
minted with the same id in both; a disagreement between them is a finding.

**The grammar.** An id is the prefix, a dot, then one or more segments joined by dots; a
segment is `[A-Za-z0-9_-]+`. No space, slash or parenthesis. Slug at mint time, and slug
a period as `scripts/periods.py` keys it (e.g. `fy2025`, `2026-03`, `ltm_2026-07`). The
column label (`LTM July 2026`) is display, carried by `label`, never by the id.
`check_workbook.py --run-dir` refuses an id outside the grammar at the check's own gate;
`resolve_roots.py` refuses it at the seal.

**The ledger shape.** A `workpapers/*.yaml` ledger is a YAML list at its top level, one
`- id:` mapping per record, as every example below is written. Never a mapping keyed by
id, and never the list wrapped under a key (`figures:`). `check_workbook.py --run-dir`
refuses any other shape at the check's own gate; `resolve_roots.py` refuses it at the
seal.

## 1. Citations

A citation records one read. Its kind follows the read: an aggregate over rows is a
**span**; one stated figure is a **cell**; reliance on what a document says in prose or on
a slide is a **passage**. Never synthesize a cell list for an aggregate; never widen a
single stated figure to a span.

### span

```yaml
- id: E.gl_detail.fy2026
  kind: span
  file: "gl/GL Detail FY2026.xlsx"    # relative to the source path the run was given
  source: gl                          # the run's source id
  file_role: system_export            # system_export | management_prepared | bank_statement
                                      # | policy_document | correspondence | unknown
                                      # | run_artifact (a file this run wrote; add from_check)
  sheet: "Detail"
  header_at: "A4"                     # the cell holding the header row
  rows: "5:31882"                     # the data rows consumed
  columns:
    - {name: "Amount",  at: "F", holds: values, parse: "number; parentheses negative"}
    - {name: "Account", at: "B", holds: values, parse: "text"}
  filter: "none - full sheet consumed"
  row_count: 31878
  control_total: {column: "Amount", value: 12094418.55}
  value_source: cell_values           # cell_values | cached_formula_results
  read_at: "2026-08-25"
  note: >-
    Anything a re-performer needs in order to select the same rows.
```

`control_total`, `header_at`, `rows`, `holds` and `filter` are required. A read of the
whole sheet states `filter: "none - full sheet consumed"`.

A file whose columns sit by position — a fixed-width export, a PDF statement's text
layer — is cited the same way, with `rows` and `at` as the reading step states them:
each column's `at` is its character range (`chars 41-50`), `header_at` states
`none - columns by position` (or the header's line), and a PDF's `rows` are page and
line ranges of its text layer (`p1:L5-7,p2:L4-5`). A re-performer opens the page, reads the lines named and cuts the characters named.

A read of a file the run wrote, e.g. another check's item table under `checks/`, is
`file_role: run_artifact` with `from_check: <check id>`, never `system_export` or any
data-room role. Its basis is the producing check's own citations, and the deliverable
presents the read as derived.

**A span is measured.** A run whose plan scheduled an `extract` step (`PLAYBOOKS.md`
§ The file) holds the tables its steps read under `<run_dir>/cache/`, written by the
extract step's script through `scripts/cache.py` with true file coordinates and each
column's parse (`RUN_CONTRACT.md`, the file table). A step reads a population with one
SQL statement through `scripts/evidence.py select`, which returns the rows and their
span: coordinates and columns from the manifest, `filter` as the WHERE clause verbatim
in the file's own column names, `row_count` and `control_total` measured over the rows
returned. A span cites one table; a join across two files is two spans, and the
figure's `expression` carries the arithmetic. The parquet is named nowhere: a reader
holding the workbook and the data room opens the file at `header_at`, reads the columns
as their `parse` says, applies the filter, counts the rows and sums the control column.
A file the step reads directly is parsed in its own code and cited with
`span(frame=<the parsed df>, file=, source=, file_role=, sheet=, header_at=, rows=,
columns={name: {at, parse}}, filter=, control=)`: the step states the coordinates and
parse, and the count and total are measured over the frame.

**A control total is never taken over a column with an unparsed cell.**

### cell

```yaml
- id: E.tb.ar_control_2026-03
  kind: cell
  file: "tb/TB 2026-03.xlsx"
  source: tb
  file_role: system_export
  sheet: "TB"
  cell: "D41"
  label_from: "B41 = '1200 - Accounts Receivable'"
  value: 9438108.22
  cell_kind: literal                  # literal | formula
  formula: null                       # present iff cell_kind: formula
  read_at: "2026-08-25"
```

`label_from` is required. Where the cell is a formula, record it and expand its references
exactly one hop, with value and kind at each target; a deeper hop is a separate citation.
A hop that dead-ends records a `gap_reason`.

### passage

For a read of prose or slides, e.g. a management comment, a memo section, a board-deck
page:

```yaml
- id: E.close_memo.bank_fees
  kind: passage
  file: "close/March close memo.pdf"
  source: close
  file_role: management_prepared
  locator: "p. 3, under 'Bank fees'"
  quote: "<the sentences relied on, verbatim, kept short>"
  read_at: "2026-08-25"
```

A passage records what a document says and where. A figure may cite one as `as_stated`
support or as the evidence behind a `candidate` explanation (DOCTRINE.md § Resolving
issues). Arithmetic never runs over a quote.

## 2. Read the formulas, not only the values

- A derived column keyed off `TODAY()` changes value each time the file is opened.
  Re-derive it from the underlying dates and say so in the citation's `note`.
- A stated figure whose formula input is a typed literal is an assertion, not a
  measurement. Record it as one.
- A column that `holds: values` where formulas were expected is recorded as found.

## 3. Figures

Every number in the deliverable traces to a figure; the deliverable never cites a citation
directly. One entry per stated figure. One entry per projected table, citing its span;
that entry covers the table's cells.

```yaml
- id: F.tie_gl_tb.delta
  label: "GL roll-up to TB - difference at 2026-03-31"
  value: 3306.11
  unit: usd                           # a `figures.UNITS` unit
  expression: "F.tie_gl_tb.gl_side - F.tie_gl_tb.tb_side"
  inputs:
    - {role: gl_side, source_type: figure, figure_id: F.tie_gl_tb.gl_side}
    - {role: tb_side, source_type: figure, figure_id: F.tie_gl_tb.tb_side}
  population: {ref: P.gl_postings_fy2026}
  zero_basis: null                    # required when value is 0, null or blank
  caveats: [T.gl_tb.2026-03]
  disposition: measured               # measured | inferred | as_stated
```

**Write the ledger through `scripts/figures.py`.** `Ledger(run_dir, check)` holds the
check's figures, populations and citations. `fig()` checks each field below when it is
minted. `write()` resolves every input, population, citation and `F.`/`P.`/`E.` id in an
`expression` against the run's ledgers, and refuses the whole write, naming each dead
end, when one does not resolve: the one-hop contract is kept at the check, not repaired
at the seal. `Ledger.tie()` mints a tie's difference figure and classifies it
(check-tie SKILL § 4). A step never writes its own `fig()`.

- **`inputs[]` is never empty, and `role` is required.** `source_type` is one of
  `room_file` (with `citation_id`: a read of a file the user gave us), `figure` (with
  `figure_id`), `check_output` (with `citation_id`: a `run_artifact` read of another
  check's item table; never labeled `room_file`), or `declared` (with `field`: a
  tolerance or option the user declared). A passthrough records
  `expression: "as stated at E.x (passthrough)"` and its input.
- **`zero_basis`** on any zero, null or blank value: `measured_zero` (requires
  `population.included_n > 0` and a non-empty citation `filter`), `not_measured` (a
  coverage statement; never written into the deliverable as a value), or
  `not_applicable` with a reason.
- **`population`** is a `P.` reference or inline `{total_n, included_n, exclusions[]}`.
  When `included_n < total_n`, every exclusion is named with its count, and the narrowing
  is stated where the figure is first presented.

## 4. Figures in the deliverable

**Every figure cell in a workbook carries its computed value.** openpyxl writes a formula
with no cached result, and the cell renders blank in a viewer that does not recalculate.
Write the value (the arithmetic lives in the figure's `expression` on the Sources tab), or
write the formula with its result cached beside it. The gate is
`scripts/check_workbook.py`. A typed constant that resolves to no figure id is blocking.

**Prose numbers are interpolated, never typed.** A sentence is authored as a template
around a figure id; the code that writes the tab or the deck loads the ledger and
substitutes the value, formatted per `DOCTRINE.md` § Number conventions —
`Ledger.sub("... {F.a5.nrr.fy2025} ...")` or `figures.fmt(value, unit)`, one formatter
for every tab and the deck. The gate is
`scripts/check_prose.py`: it extracts every dollar amount, percentage and multiple from
text and refuses any that no ledger value backs within rounding tolerance. A declared
tolerance a sentence states is admitted with `--allow`.

**Every presented figure re-performs in one hop.** The Sources tab carries, beside each
figure's `expression` and inputs, its **root source** (the citation ids reached by
collapsing every passthrough and figure-to-figure hop) and a **To reperform** recipe:
file, sheet, rows, columns, filter, arithmetic, expected value. The Evidence tab carries
the citation records merged from `workpapers/evidence-*.yaml`. A reader holding only the
workbook and the data room can re-select the same rows; the run directory is never
required reading. Layout and assembly: check-report SKILL § 1; the gate is
`scripts/check_workbook.py`.

**An id sits alone in its cell.** `link_workbook.py` links a cell that is exactly one id to
the cell where it resolves. Where a row cites several ids, spread them across adjacent
columns.

## 5. Item tables

Item-level work is written down, not only summarized. A check that matches, traces or
pairs rosters at item grain writes one CSV per item table at `checks/<check>-<table>.csv`
(each kind's SKILL.md names its own tables and columns) plus a manifest block in
`checks/<check>.md` recording what built it: the citations behind each side, the keys
used, `row_count`, and a control total per side. The report and a re-performer read the
table; the ledger's figures cite the citations; the manifest block is the hop between
them. A fix re-run that moves the check's figures rewrites its own tables in the same
pass; no other step edits them.
