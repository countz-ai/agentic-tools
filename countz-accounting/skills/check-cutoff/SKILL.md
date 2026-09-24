---
name: check-cutoff
description: >-
  Perform one cutoff check: establish that activity around a period end is recorded in
  the correct period on both sides — book postings to bank lines and back inside a
  declared window, or interbank transfers paired across accounts — with every
  wrong-period item an exception.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one cutoff check

Arguments: `run_dir`, `seq`, `check` (the check id), `sources` (comma-joined source ids —
the books side first, the evidence side second), `goal`, `params` (the period end and the
window — see below; `items_from` where in-transit items come from a reconciliation),
`mode` (`fresh` | `fix`), and on `fix`, `findings_from`.

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` (§ Voice),
`${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md` (§ 3 and § 5), then `sources/<id>.md` for
each source where it exists (a plan-driven run's planner writes the profiles; derive
your own binding where none answers it), and the dependency's record where
`params.items_from` names one.

Throughout, *bank* reads as the evidence side: the bank for a cash cutoff; the delivery,
acceptance, service or fulfillment record a recipe family names otherwise.

## 1. Define the window

The period ends and window come from `params` (keys: `scripts/periods.py` `cutoff_spec`).
**Never assume a window**, and never type one: compute it with `scripts/periods.py` —

```python
from periods import cutoff_spec
spec = cutoff_spec(params)          # the same function the gate refuses with
for pe, (start, end) in zip(spec["period_ends"], spec["windows"]):
    ...
```

— so the dates on the tab are the dates the gate validated. A dispatch without a window
is recorded as a blocker. Place each posting and each bank line on its **local** date:
filter with `Period.mask` / `local_date`, which convert a timezone-aware timestamp to
`params.timezone` before taking the date (a UTC export otherwise moves a 23:30 posting on
the period end into the next period), and refuse a timezone-aware column when no zone is
declared. State the populations: every book posting and every bank line dated inside the
window, each side with its count and control total, cited as spans.

## 2. Trace both directions

Pair with polars joins, one per pass; check the assignment with
`${CLAUDE_PLUGIN_ROOT}/scripts/matching.py`'s `check_assignment()` before writing it.

- **book → bank**: every book posting in the window resolves to a bank line with its
  date, or to an in-transit item on the period-end reconciliation (`params.items_from`).
- **bank → book**: every bank line in the window resolves to a book posting with its
  period.

Write `checks/<check>-window.csv` — side, date, amount, reference, matched-to, book
period, bank date, classification — with its manifest block in `checks/<check>.md` per
EVIDENCE.md § 5. Matched plus unmatched per side must equal that side's population.

## 3. Transfers, where the goal names them

Identify bank lines that move money between the run's own accounts inside the window
(the accounts from `params` or the run's sources); pair out-side to in-side across
accounts by amount and date, each pair's book entries read for their periods. An unpaired
side, or a pair whose book entries straddle the period end, is an exception — that shape
counts one balance twice at the period end, and the schedule says which direction.

## 4. Classify every item

`in_period` | `in_transit_on_rec` (cited to the reconciliation's item) | `wrong_period` —
an `X.` exception with both dates, the amount, and the direction it moves period-end
cash | `unmatched` — an `X.` exception naming the side with no counterpart. Never
reassign an item's period to make the window close.

## 5. Files

- `checks/<check>.md` — the window and who declared it, both populations, the tracing in
  each direction, the transfer pairing where one ran, and the classifications.
- `checks/<check>-window.csv` — the window table of § 2, with its manifest block.
- `out/tabs/<check>.xlsx` — your tab, blocks per `WORKBOOK.md` § 4, with the window
  schedule as the primary table, the transfer pairing where one ran, and the exceptions.

Close `checks/<check>.md` with the answer: whether every item fell in its correct period.
Then the items you resolved and the caveats the reader must weigh, the wrong-period and
unmatched items still standing, and either side's window population you could not
establish.

Stage, gate and rename per `WORKBOOK.md` § 8.

## `mode: fix`

Exactly as `check-tie`: address every finding naming your check, rewrite only your own
files — the window table included.

## Record

Write `steps/<NNNN>-cutoff.json` per `RUN_CONTRACT.md`: `check_id`, `produced`,
`consumed` with mtimes, `blockers`. `conclusion` states the window, the items tested, and
the wrong-period amount in dollars, in two sentences. Return at most ten lines.
