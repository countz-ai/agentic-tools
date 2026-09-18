---
name: check-recon
description: >-
  Perform one reconciliation: explain the difference between two related records through
  item-level matching and classified, evidenced reconciling items, with any residual
  stated as unexplained.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one reconciliation

Arguments: `run_dir`, `seq`, `check` (the check id), `sources` (comma-joined source ids —
the first is the subject side, the books; the second the counterparty side, the
statement), `goal` (the user's stated goal, or `(none)`), `mode` (`fresh` | `fix`), and on
`fix`, `findings_from`.

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` (§ Resolving issues, § Voice),
`${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md` (§ 5 for the match table), then
`sources/<id>.md` for each source, where it exists — a plan-driven run's planner writes
the profiles; derive your own binding where none answers it.

## 1. Define the reconciliation

State before computing: the two quantities and why they are expected to differ, the
population and period on each side, and the closing figures being bridged. Where the goal
is `(none)`, the default is bridging the two closing balances at the latest common date,
stated as such. If the sources are two records of the same quantity that should simply
agree, say so in `blockers` — that is a tie-out, and running it here invites explaining
away a difference that should not exist.

## 2. Establish both sides

Closing figures and populations from each source at full precision, each with its citation
in `workpapers/evidence-<check>.yaml` and its figure in `workpapers/figures-<check>.yaml`.
Take the difference before explaining anything.

## 3. Match at item level

Where both sides carry item grain, match — by reference, then amount-and-date, then
looser keys, each pass recorded. One-to-many matches are allowed and recorded as such.
Write the match table `checks/<check>-matches.csv` (side, match key, date, amount,
matched-to, classification) with its manifest block in `checks/<check>.md` per
EVIDENCE.md § 5: the citations behind each side, the keys used, `row_count` and a control
total per side. The population accounting must close: matched plus unmatched per side
equals that side's citation `row_count` and `control_total`.

Where a side has no item grain, say so; the reconciliation degrades to
closing-figure-plus-known-items, and the record states the reduced strength.

## 4. Classify the unmatched

Every unmatched item lands in a class — timing (deposits in transit, outstanding
payments), items on one side not recorded on the other (fees, interest), errors (with the
correcting side named), or unexplained. Each reconciling item `RI.<slug>` is quantified
from its OWN composing items — listed, with citations — never backed out of the gap
(DOCTRINE.md § Resolving issues). A `candidate` explanation (plausible, needs the user or
management to confirm) is presented as such and never netted into the bridge.

## 5. The reconciliation statement

Side A, the classified reconciling items, the unexplained residual as its own labelled
line, side B — footing exactly at computation precision (no plug, no `other`, no
scaling). An unexplained residual is stated with its magnitude; where it is material
to the goal, the check says so plainly and the residual carries a data request.

Files:

- `checks/<check>.md` — the definition, the sides, the match summary by pass, the items
  with their evidence, the elections where any, and the statement.
- `checks/<check>-matches.csv` — the match table of § 3, with its manifest block.
- `out/tabs/<check>.xlsx` — your tab, blocks per `WORKBOOK.md` § 4, with the
  reconciliation statement as the primary table and the item schedules.

Close `checks/<check>.md` with the answer: whether the difference is fully explained.
Then the residual left unexplained beyond rounding, whether it is material, the caveats
the reader must weigh (carry-forwards as in `check-tie`), and any side you could not
establish with no defensible election available.

Stage, gate and rename per `WORKBOOK.md` § 8.

## `mode: fix`

Exactly as `check-tie`: address every finding naming your check, record what changed and
what you disagree with, rewrite only your own files — the match table included.

## Record

Write `steps/<NNNN>-recon.json` per `RUN_CONTRACT.md`: `check_id`, `produced`,
`consumed` with mtimes, `blockers`. `conclusion` states the difference, how much is
explained, and the unexplained residual in dollars, in two sentences. Return at most ten
lines.
