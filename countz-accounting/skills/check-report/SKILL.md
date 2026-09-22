---
name: check-report
description: >-
  Assemble the deliverable from the run's checks: the workbook, the report deck, and the
  run summary. Copies the check tabs; writes only the run-level surfaces and the deck's
  source document.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Assemble the deliverable

Arguments: `run_dir`, `seq`, and optionally `title` and `note` (from a playbook's `report`
block — the note goes on the deck's first page).

Read `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` § Voice and § Number conventions,
`${CLAUDE_PLUGIN_ROOT}/reference/WORKBOOK.md` (where the reader's eye lands on every tab —
the map, the frozen band, the run-level tabs), `reference/WORKBOOK_STYLE.md` (how a
cell looks; the kit every tab script starts from) and `reference/REPORT.md` (the deck:
the brief, `report.yaml`, the gate), then `run.json` (the check roster and
statuses), the latest review record, every `checks/<check>.md`, and the ledgers. Each
check wrote its own tab; **you copy tabs, cached values intact — never rewrite one.** A
rostered check with no tab gets no empty tab; it is stated in coverage.

## 1. The workbook — `out/workbook.xlsx`

The tab strip, the band and the content of every run-level tab are `WORKBOOK.md` § 2
and § 6. Copy each check's tab cell by cell with its resolved formatting; write
the run-level tabs yourself.

**Exec Summary.** Read the recipe's `## Exec summary` (the recipe is at
`run.json.plan.recipe`) and tell that story from the checks' results, in whatever form
carries it — sentences, tables copied from check tabs, charts over them — under the
rules in `WORKBOOK.md` § 6. The headline check is the one in `run.json.checks` whose
`params.family` matches the recipe's `headline`; its walk's spine — starting figure to
closing figure, one row per item the walk includes, grouped under its rung — is the
schedule the story is most often built on. A run with no recipe tells the story its
objective and results support.

**Sources.** Collapse the roots first, never by hand:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_roots.py <run_dir>
```

It renders, per figure, the root citation ids, the derived citations crossed, the
declared fields relied on and the collapsed depth, and per ledger file the entries it
contributed. An `unresolved` entry is a ledger reference nothing defines — a blocker
against the check that cited it, never patched here. Exit 2 is a refused ledger — a
top level that is not a list, an id outside the grammar (EVIDENCE.md § 0) — named on
stderr with its file: the owning check's to rewrite. Do not normalise a copy and
proceed; end the step `blocked` naming that check (§ 6).

**Links.** After assembly:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/link_workbook.py <run_dir>/out/.staging/workbook.xlsx
```

It wires every id and every Exec Summary amount to where it resolves. It reports the
ids it cannot wire: fix each by stating the id where it
resolves, never by dropping the citation; fix an unmatched amount by copying its row
label and column header verbatim, never by placing a link. Citations to the user's
files stay text — file · sheet · cell — never file links.

## 2. The report deck — `out/report.pptx`

The deck is for the decider; the workbook is for the reviewer who checks it
(`WORKBOOK.md` § 1). The brief and its three rules are `REPORT.md` § 1 — read it before
planning. What this step writes:

- `out/.staging/report-plan.md` — the plan, before any page: the story in a few
  sentences, then the pages in order, each with its one message and the tabs it draws
  on. The order is `REPORT.md` § 1: the opening — the `Executive summary` page, whose
  `message` is the one sentence the deck exists to deliver, with the stat tiles, chart
  or table that carry it; then the key-metrics page, headed as the recipe's
  `metrics.title` (RECIPE_FORMAT.md § Report; the recipe is at `run.json.plan.recipe`)
  and showing the figures its prose names; then at most one page carrying the story to
  the first schedule. Then the recipe's `## Report` schedules, in the recipe's order,
  one `table:` block each with the schedule's own keys (`from`, `columns`, `where`,
  `through`, `periods`, `scale`, `dense`) — `columns:` on the block names the tab's
  actual headers that carry the recipe's words, with every period column for
  `periods: all` and the last for `latest`. Never `max_rows` on one: a long schedule
  continues over pages. The narrative pages after refer to those rows and copy no
  schedule again. A run with no recipe opens on the `Executive summary` page the same
  way and goes straight to its narrative.
- `out/.staging/report.yaml` — the pages to the plan (`REPORT.md` § 2). A page's
  `title` is its headline — the subject of a page of figures, the conclusion of a page
  that argues one — and the sentence stating the message, where the page needs one, is
  `message`; every sentence on a slide is complete.

Read `REPORT.md` § 3 for the words and § 4 for the numbers before writing pages; no
other check reads either. Rules a finished deck got wrong:

- Write to the company's own executives and operators unless the run declares a
  transaction reader.
- State the basis in words: *as instructed*, not *as the user declared*; *this report*,
  not *this run*; a category, not a *bucket*. Retitle a copied table with `title:` where
  its own title carries one of these.
- Call a measure what the workbook calls it: *best-possible days sales outstanding*, not
  *the floor*.
- Cut a line whose point is its phrasing; state the finding instead.
- Name the population a share is of.
- Write figures as `$50.5m` and `57.8 days`, and declare `scale: thousands` on a schedule
  of dollars.
- Define an object where it first appears — the record it comes from, how many there are,
  what they are called, the amount behind it — and carry that name on every page after.
- Build the page on what is open from the Open Items tab: each item with its size, the
  function that answers it, and what the answer decides.
- A table appears once. A narrative page that needs a schedule's figure references the
  cell or states it in a stat tile; it does not copy the rows a schedule page already
  shows.

Then build:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_report.py <run_dir>
```

A reference the builder cannot resolve is named on stderr: fix it by copying the label
and header from the tab, never by typing the value. A page the builder reports as
overflowing is split or trimmed, never squeezed.

## 3. Gates

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_workbook.py <run_dir>/out/.staging/workbook.xlsx \
    --run-dir <run_dir>
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_prose.py <run_dir>/out/.staging/workbook.xlsx \
    --run-dir <run_dir>
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_report.py <run_dir>/out/.staging/report.pptx \
    --run-dir <run_dir>
```

`check_workbook.py` gates the workbook: cached values, the id links § 1 wires, and the
reperformance contract — it refuses an external or broken link, an unwired id cell, a
dead-end id (one cited but resolving nowhere), a number on the Exec Summary with no link
to what it was copied from, an `E.` id in a workbook with no Evidence tab, a Sources tab missing the `root source` / `To reperform` columns, a figure row
whose `To reperform` cell is empty, a pane frozen deeper than the header band
(5 rows / 2 columns) on any tab, and a tab strip that is not the reader's path
(WORKBOOK.md § 2) —
with `--run-dir` it computes the order from the roster and the recipe's `lead` and
names the strip it wants. `check_report.py` gates the deck (`REPORT.md` § 5): every number on
a slide backed by a workbook cell or a ledger record, every figure page naming its source
tabs in the footer, every title a headline and every sentence complete. **A non-zero exit is a stop — the deliverable does not
seal (§ 6).** On a surface YOU wrote — a run-level tab, `report.yaml` — fix it and
re-gate. On a copied tab you may not repair it: name the cell or the id,
name the check that wrote it, and end the step `blocked` so the run re-runs that check. A
dead-end ledger id is the owning check's record to write even when the citation sits on
the Sources or Evidence tab you assembled — those tabs are merged from
`workpapers/*.yaml`, so an id no record declares cannot be repaired here either. Also
assert the open-item
accounting balances (every finding `fixed`, `carried_to_open_items` or `withheld`; the
counts sum; every carried item names its `from_finding`) and that the deck and the
workbook agree in both directions — a reader of the executive summary and a reader of
the schedule must not come away with different open items.

## 4. What the run did not do

Every check that did not run or ended blocked or failed, every check that could not
establish what it set out to establish, and every step that ran degraded, is listed on
Basis of Preparation and stated in the deck. Where one limits the
answer, the Exec Summary and the deck say so.

## 5. The run summary — `out/RUN_SUMMARY.md`

For the user, not the reader: the roster with statuses, findings that did not close
(`fix_attempted`, withheld figures) and what would close each, data gaps, and how the run
ended. Then paste, unedited, under `## What this run took`, the rendering of:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/usage_report.py <run_dir>
```

Do not retype or round its numbers, and keep the line about rates being estimated. Write
the machine form beside it with `--json > <run_dir>/out/usage.json`. Close with one line
telling the user an instruction against any item re-runs the owning check and reseals the
report.

## 6. Snapshot and record

Copy the sealed workbook and deck to `out/history/<NNNN>-workbook.xlsx` and
`out/history/<NNNN>-report.pptx` — re-assemblies overwrite `out/workbook.xlsx` and
`out/report.pptx`, and the snapshot is what lets a human restore an earlier accepted
version by hand. Stage everything in `out/.staging/`, rename into place as your last act
— `workbook.xlsx`, `report.pptx`, `report.yaml`, `report-plan.md`, `RUN_SUMMARY.md`.
**The rename is the seal, so it happens only once § 3's gates exit 0.** A gate still
failing means the run is not finished: leave `out/.staging/` where it is, write the step
`outcome: blocked` with `error: null` and one `blockers` entry per failing gate — `what`
holds the gate's own output verbatim, `effect` names the checks that must re-run — and
put those checks in `conclusion`. Never put the gate's output in `error`: `error` means
you could not do your work, and a failed step is retried — a re-run of the same gate to
the same answer.
Write `steps/<NNNN>-report.json` with `produced` naming the workbook, the deck, its
plan and source, the summary and the snapshots. Return at most ten lines.
