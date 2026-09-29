---
name: check-vouch
description: >-
  Perform one vouch: trace every item on an asserted list — reconciling items on a
  period-end reconciliation, a schedule's rows — to its clearing or supporting line in a
  named target source, with every untraced item an exception.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one vouch

Arguments: `run_dir`, `seq`, `check` (the check id), `sources` (comma-joined source ids —
the target sources the items are traced INTO, subsequent statements typically), `goal`,
`params` (must name where the items come from — see below), `mode` (`fresh` | `fix`),
and on `fix`, `findings_from`.

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` (§ Voice),
`${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md` (§ 3 and § 5), then `sources/<id>.md` for
each target source where it exists (a plan-driven run's planner writes the profiles;
derive your own binding where none answers it), then the item origin.

## 1. Establish the item population

The items come from a record, never from prose: `params.items_from` names a terminal
check in this run — read its `checks/<id>.md` and tables for the item list (that check is
a declared dependency of yours, terminal before you started) — or `params` names the
list the user supplied (`items_file`, `items_sheet`, `items_range`), cited like any
other read. `check_playbook.py` refuses a vouch declared with neither. Record the population:
every item, its count and control total, in your ledgers. The item accounting must
consume the whole list — every item on it ends with a classification, none dropped.

## 2. Trace each item

Trace with polars joins, one per pass; check the assignment with
`${CLAUDE_PLUGIN_ROOT}/scripts/matching.py`'s `check_assignment()`, and classify what no
pass clears per § 3.

Into the target source at item grain: the clearing or supporting line's citation, its
date and amount. One-to-many is allowed and recorded (a deposit clearing as two credits).
Write `checks/<check>-items.csv` — item, origin reference, amount, target citation,
cleared date, days outstanding where the origin carries its date, classification — with
its manifest block in `checks/<check>.md` per EVIDENCE.md § 5.

## 3. Classify every item

`traced` — cleared inside the expected window (from `params`, or the target's covered
period stated as the default); `traced_late` — cleared, outside it, with the dates;
`not_traced` — an `X.` exception with the item, its amount, its age where known, what
would clear it, and who owns that; `unable` — the target does not cover the item's
window, recorded in `blockers` and the check degraded, never counted as traced or as an
exception.

## 4. Files

- `checks/<check>.md` — the item population and the record it came from, the tracing, and
  every item's classification.
- `checks/<check>-items.csv` — the items table of § 2, with its manifest block.
- `out/tabs/<check>.xlsx` — your tab, blocks per `WORKBOOK.md` § 4, with the vouch
  schedule as the primary table and the exceptions.

Close `checks/<check>.md` with the answer: whether every item traced inside the window.
Then the items that did not trace, the caveats the reader must weigh — late clearings,
one-to-many splits — and whether the item population could be established at all.

Stage, gate and rename per `WORKBOOK.md` § 8.

## `mode: fix`

Exactly as `check-tie`: address every finding naming your check, rewrite only your own
files — the items table included.

## Record

Write `steps/<NNNN>-vouch.json` per `RUN_CONTRACT.md`: `check_id`, `produced`,
`consumed` with mtimes (the dependency's record included), `blockers`. `conclusion`
states items traced over items listed and the untraced amount in dollars, in two
sentences. Return at most ten lines.
