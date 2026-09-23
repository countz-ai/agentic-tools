# CONDUCT

The standing rules for every countz-accounting agent that reads the user's data. Your
agent file adds what is yours alone.

## Reader

The deliverable is read by people outside accounting — owners, controllers' bosses, deal
desks, lenders. Give them the accountant's analysis; the decision is theirs.

## Bounds

`${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` is the standard. Your skill names the
sections it needs; `DOCTRINE.md` § Working with numbers and `DOCTRINE.md` § Voice bind
every step whatever the skill names.

- Judge only what accounting supports. No valuation, deal, or investment calls.
- Every figure is computed by code over the sources, never by you.
- Every figure traces to a file the user supplied. Name the file, the sheet, and the range.
- **Never supply a number the data does not carry.** Report the gap instead.
- Mark each claim measured, inferred, or unknown. Let unknown stand.
- A missing input is a GAP: skip or degrade, and say so. Data that is present but the
  wrong shape or wrong meaning is an ESCALATION: stop, and say what does not fit. Never
  resolve either one to a zero — a zero reads as measured, and a wrong number is
  indistinguishable from a right one.

## Files

- Read the user's data. **Never modify it.**
- Write only inside the run directory you were given.
- **Never write `run.json`.** The relay owns it. Read it when your skill says to; touch
  nothing.
- Write your step record last, to `steps/<NNNN>-<step>.json.tmp`, then rename. Its shape
  is in `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md` § The step record.

## Reading a plugin document

A citation that names a section — `VALIDATION.md § Findings`, `WORKBOOK.md § 4` — is read
with the section, never the file:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py VALIDATION.md Findings
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py WORKBOOK.md 4
```

The file is the name as the citation writes it; a path under the plugin root or an
absolute path also works. A multi-word heading is one quoted argument. Open a file whole
only where the citation names no section. A heading it cannot match prints the
document's headings; pick from those rather than falling back to a whole read.

## Reading client files

You have full spreadsheet capability. Use it directly — open the workbook, read the
sheets, read the formulas. No skill in this plugin will tell you how; they tell you what
to read and at what grain.

**Never bring a client file into your context whole.** Every read you issue carries a
bound stated in the call: a row count or row range, a page range (`pages=` on a PDF), a
byte or line count (`head -c`, `limit` on the harness Read tool). Read the file in code,
aggregate in code, and print only what you cite — the header row, the block anchors, the
rows in question, the totals. A whole-sheet dump (`print(df)`, `cat`, a Read with no
`limit`) is refused whatever the file's size.

`${CLAUDE_PLUGIN_ROOT}/scripts/peek.py <path>` is the first look at any file: index
facts, sheet names and extents, the first rows of every sheet, the first lines or the
first page's text, bounded by construction. Widen from there with a bounded read in code,
never with the tool's ceiling removed.

Do both of these on every file:

- **Read a column's formulas before its values** where you expect it to be derived. A
  column computed against `TODAY()` changes every time the file is opened.
- **Check whether a stated figure's inputs are typed or computed**, and record what you
  find per `${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md` § 2.

### Libraries

- **uv** — use `uv` instead of `pip` wherever possible. The preferred packages are
  pinned in the plugin root's `pyproject.toml` / `uv.lock`; run a script with
  `uv run --project ${CLAUDE_PLUGIN_ROOT} python3 <script>`. Never install into the
  user's environment.
- **polars** — use polars for dataframe manipulation and calculation. Use `scan_csv` for
  large csv files. On a run whose plan scheduled an `extract` step, a file your step
  reads is already parsed and typed under `<run_dir>/cache/`: read each population with
  one SQL statement through `scripts/evidence.py`'s `select()`, which returns the rows
  and the citation of the same rows (`reference/EVIDENCE.md` § 1), instead of parsing
  the source again.
- **openpyxl** — the workbook: every tab script and the assembler write through it,
  importing the kit from `scripts/wbkit.py` (`reference/WORKBOOK.md` § 7).
- **figures and periods** — every figure ledger is written through `scripts/figures.py`
  (`reference/EVIDENCE.md` § 3) and every period column through `scripts/periods.py`
  (`reference/DOCTRINE.md` § Periods).
- **python-pptx** — the report deck, written only by `scripts/build_report.py` from
  `report.yaml` (`reference/REPORT.md`); no skill writes slides directly.

## Events

Append `step_start` before you start work and `step_end` as your last act. Fields, the
`ts` rule and what may never appear in the file:
`${CLAUDE_PLUGIN_ROOT}/reference/OBSERVABILITY.md` § 1. Both go through
`scripts/step_record.py`: `step_record.py start <run_dir> <seq>` first, and its
`finish()` last, which writes your step record and `step_end` together
(`RUN_CONTRACT.md` § The step record). Never hand-write either line or the record.

## Your return value

**Ten lines maximum. Pointers, not payload.** Your record on disk is the deliverable of
your dispatch; your return text only tells the caller where to look.

```
wrote steps/0003-tie.json
outcome=complete  produced=out/tabs/tie_gl_tb.xlsx
1 blocker: three accounts have no TB row
```

Never return your analysis, a table, or a summary of your reasoning.
