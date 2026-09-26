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

Where both sides are items that settle each other — invoices and the deposits that paid
them, book entries and statement lines, bills and payments — match with
`${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py` (its docstring is the method and the
contract); write no matching passes of your own. Your part is the mapping: each side as a
stream of `id`, `date`, `value`, and `entity`, `ref` and `text` (a description, a memo,
a payer name) wherever the source carries one. Measure the date on
which the two sides agree, and the lag between them, before you choose it: the `window`
is that measured lag, and `split_days` the span over which part payments are seen to
arrive, zero where the data shows none. State both as elections.

Elsewhere, match with polars joins, one per pass — by reference, then amount-and-date,
then looser keys, each pass recorded. One-to-many matches are allowed and recorded as
such. Either way, check the assignment with
`${CLAUDE_PLUGIN_ROOT}/scripts/matching.py`'s `check_assignment()` before writing it.

A group is matched only where its two sides agree to the cent. Which counterparty item
carries an item (a bank row id against an invoice) is `resolve.py`'s `link`, with its
basis: `allocation` is proved to the cent; `anchor` is proved by entity and date under a
rule the engine trusted only after testing it on the proved items (`calibration`, stated
in the record); `solver` and `remainder` links are inferences and carry a flag. Every item with a `review` flag is yours to settle before the table is
written: read what the engine cannot — names, memo text, the rest of the data room —
and either confirm the link with the evidence that settles it, narrow a set to its one
item, or leave it flagged as an open item. `note` carries the arithmetic to read them
with: what each open group is over or short by, and which open items equal it. Report links by basis, and the flagged ones
as their own count.
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
correcting side named), or unexplained. Before calling an item unexplained, test whether
its cash is on the other side at another grain: an unmatched item and an unmatched
counterparty item of the same entity and period are one question, not two, and the
bridge carries them together, stated as cash the files cannot place at item grain, with
the document that would place it. Each reconciling item `RI.<slug>` is quantified
from its OWN composing items — listed, with citations — never backed out of the gap
(DOCTRINE.md § Resolving issues). A `candidate` explanation (plausible, needs the user or
management to confirm) is presented as such and never netted into the bridge.

## 5. The reconciliation statement

Side A, the classified reconciling items, the unexplained residual as its own labeled
line, side B — footing exactly at computation precision (no plug, no `other`, no
scaling). An unexplained residual is stated with its magnitude; where it is material
to the goal, the check says so plainly and the residual carries a data request. A line
whose components offset states its gross beside its net — the unmatched count and amount
on each side — wherever its net is stated, the answer included.

Files:

- `checks/<check>.md` — the definition, the sides, the match summary by pass, the items
  with their evidence, the elections where any, and the statement.
- `checks/<check>-matches.csv` — the match table of § 3, with its manifest block.
- `out/tabs/<check>.xlsx` — your tab, blocks per `WORKBOOK.md` § 4, with the
  reconciliation statement as the primary table and the item schedules.

Close `checks/<check>.md` with the answer: whether the difference is fully explained,
and at which grain the items are proved — linked, tied in groups, or open.
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
