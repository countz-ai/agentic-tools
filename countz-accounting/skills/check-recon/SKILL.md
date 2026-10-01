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

Where both sides are records of the same money — the book's deposits and the statement's
credits, its payments and the statement's debits, invoices and a cash-application file —
match with `${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py` (its docstring is the method and the
contract). It matches by ordered rules, as reconciliation software does, and every match
names its rule.

Match adjacent records, never across them. An invoice is settled by a payment through
cash application, and the payment reaches the bank inside a deposit: reconcile invoices to
the cash-application record, and the book's deposits to the statements, one call each,
then trace each invoice end to end with `chain()`, which reports where each one stops.
Where the data room has no cash-application record, invoices matched straight to bank
lines mostly stay unmatched (parts, lump sums, deposits of several customers); report
their payment as not established from the records, never inferred.

Your part is the mapping and the rules. Each side is a stream of `id`, `date`, `value`,
with `entity`, `ref`, `text` and `batch` wherever the source carries them: `ref` a number
both sides carry for the same thing (a cheque number on the book and on the statement),
`text` a bank description, `batch` the key the lines of one deposit share. `resolve()`
refuses a key or id held as a float or a decimal (cast it to text or an integer; for
example, Excel reads cheque 1001 as `1001.0`), a time-zoned datetime (take the entity's
local date first), date text that is not ISO, and a column a rule compares that one side
lacks. An id is unique: where the source's key repeats (a deposit id on each of its
lines, a payment id on each invoice it pays), build the id from the key and the row, and
map the key to `batch` or `ref` by what it means. One flow per call: receipts with their refunds, reversals and
returned items, or payments with theirs. Reconcile each bank account in its own call.
Measure the window before choosing it: match once by reference at any date, or on amounts
that occur once on each side, and read the days from the book's date to the bank's on those
pairs; give the few days most pairs fall in as `window`, the longest as `wide`, and, where
items take longer to reach the bank than `window` (cheques paid out), that time as
`transit=`. Pass `end=`, the statement's end date; transit and age are measured at it,
and without it at the bank's last line. Pass `same_entity=True` where both sides name
the same account or party. Add a
`Rule` with a named `difference` only for what a record says the bank keeps or converts: a
processor's fee on its settlement report, a bank's conversion on its advice; scope it to
the records it applies to with a column set only on those (the currency on a foreign
receipt and on the statement line that converted it). State each choice as an election,
with the measurement behind it.

Call `resolve()` once, over the whole population: never filter a stream first or hold
items out of it (undated items included); an item left out is a counterpart no rule
could see.

Elsewhere, match with polars joins, one per pass — by reference, then amount-and-date,
then looser keys, each pass recorded — over streams mapped as above, and read the
assignment back with `resolve.py`'s `from_assignment()`: each pass a `Pass`, its criteria
in words and, where its groups' sides differ, the difference it tolerates, named; `transit=`
measured as above. It checks the assignment with
`${CLAUDE_PLUGIN_ROOT}/scripts/matching.py`'s `check_assignment()` and returns the same
Resolution `resolve()` does, so everything below reads one `res` whichever way you matched.

Read the result the way a preparer reads auto-match output. Each match names its rule
and its match group; each unmatched item states why: no candidate, or the number of
candidates a rule found. The exceptions are yours to clear with what the engine cannot
read — names, memo text, the cash-application record, the cutoff statement — each one you
clear recorded with its evidence. Report matched by rule, cleared by you, and still open
as three separate counts.
Write the match table `checks/<check>-matches.csv` (side, match key, date, amount,
matched-to, classification) with its manifest block in `checks/<check>.md` per
EVIDENCE.md § 5: the citations behind each side, the keys used, `row_count` and a control
total per side. The population accounting must close: matched plus unmatched per side
equals that side's citation `row_count` and `control_total`.

Where a side has no item grain, say so; the reconciliation degrades to
closing-figure-plus-known-items, and the record states the reduced strength. The check
tab says it too, on a Notes line opening `No item grain:` that names the side and what its
source holds instead: it is the one reconciliation without match tabs (§ 5).

## 4. Classify the unmatched

The reconciliation statement is `res.summary`, which the reconciling items
tab shows (`WORKBOOK.md` § 6): the left items per books, less those in transit (deposits
in transit, outstanding payments: not matched, and dated close enough to the statement's
end that their bank line falls after it, by `transit`), less those not matched, each
difference a rule tolerated, plus the right items not in the book, to the right items per
bank, every line net and gross. Copy it, and classify the items `res.exceptions` lists,
with the cutoff statement (the first statement after the end) as the evidence for items in
transit and the cash-application record and the bank's advices for the rest. Never net a
line into another.

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
- `out/tabs/<check>.xlsx` — your tabs. The file opens with the match tabs, one set per
  `res` of § 3, each set under its own token, written by
  `${CLAUDE_PLUGIN_ROOT}/scripts/match_tabs.py` from it and never by hand, whether it came
  from `resolve()` or `from_assignment()`. Pass `right_population` (the bank side's
  population), and `currency` where the amounts are money: its minor units are the
  `decimals` the streams were matched at, which the call reads from `res`. Figure ids are
  `F.<check>.match.<token>.<line>`. The tabs: the match summary, the
  schedule (one row per left item, the ones kept out of the streams included as `others`:
  an invoice with no cash, each with its reason), the reconciling items and the rules
  (`WORKBOOK.md` § 6). Then your check tab, blocks per `WORKBOOK.md` § 4, with the
  reconciliation statement as the primary table and the item schedules. Every
  reconciliation carries the match tabs, so the reader finds the schedule on each one;
  `check_workbook.py` GATE 7 refuses a file without them unless the check tab states
  `No item grain:` (§ 3).

Close `checks/<check>.md` with the answer: whether the difference is fully explained,
and how the items stand — matched by rule, cleared by you with evidence, or open.
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
