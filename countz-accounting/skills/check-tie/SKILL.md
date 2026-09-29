---
name: check-tie
description: >-
  Perform one tie-out: establish that two or more records of the same quantity agree,
  resolve what does not, analyze the failures, and record the result with full citations.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one tie-out

Arguments: `run_dir`, `seq`, `check` (the check id), `sources` (comma-joined source ids),
`goal` (the user's stated goal, or `(none)`), `params`, `mode` (`fresh` | `fix`), and on
`fix`, `findings_from` (the review record whose findings name this check).

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` (§ Resolving issues,
§ Voice), `${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md`, then `sources/<id>.md` for each
of your sources, where it exists — a plan-driven run's planner writes the profiles,
and they carry the anchors and read-traps. Derive a binding yourself wherever no profile
answers it.

## 1. Define the tie-out

From the goal and the sources, state what is being agreed before computing anything: the
quantity, the population, the as-of date or period, and which side comes from which
source. One tie per asserted agreement, id `T.<slug>`; a goal that implies several — per
period end, per account — declares them all, and every declared tie ends with a status
(`pass` | `warn` | `fail` | `not_run` with a reason). Where the goal is `(none)`, the
default is the natural total-level agreement between the named sources at the latest
common date, stated as such.

A tie asserts two records of the SAME quantity agree. If what the goal
actually describes is explaining an expected difference, say so in `blockers` and record
the tie-out `not_run` — that work is a reconciliation, and running it here would report
expected differences as failures.

## 2. Compute both sides

Each side from its own source, at full precision, with a citation per read (span for an
aggregate, cell for a stated figure) in `workpapers/evidence-<check>.yaml` and a figure
per side, plus the difference, in `workpapers/figures-<check>.yaml`. Take the difference
before explaining anything.

## 3. Resolve, in order

For each tie with a difference, walk DOCTRINE.md § Resolving issues before classifying: first a
misread (wrong block, sign, gross-vs-net, subtotal swept into a sum — most differences on real
files are this; fix the read, record the trap, recompute), then a known reconciling item
quantified against its own recorded figure — never backed out of the gap — then a genuine
disagreement or gap at its measured size.

## 4. Classify, and analyze what fails

- **pass** — agreement within the display rounding unit, or within a tolerance the user
  declared (`params`). A tolerance the user did not declare is never assumed, and a
  declared one classifies the computed difference only — both sides are still summed
  over their full populations (DOCTRINE.md § Materiality). Classify with
  `Ledger.tie(id, label, a, b, tolerance=params.get("tolerance"),
  pct_tolerance=params.get("pct_tolerance"))` (`scripts/figures.py`): it mints the
  difference figure and tests `tolerance` (absolute, in the tie's unit) and
  `pct_tolerance` (a fraction of side `b`, the reference side). Where both are declared,
  the tie fails when either one fails.
- **warn** — a resolved, explained difference the reader must see. Write the
  carry-forward: one sentence with both figures, the magnitude in dollars, and the figure
  ids it affects — those figures print it at first statement.
- **fail** — an unresolved difference. Analyze it: decompose along whatever the data
  supports (by account, period, segment), quantify each component with its own evidence
  and a disposition (`supported` | `candidate` | `unexplained`), and state the residual as
  unexplained. Where the analysis must trust one side, record a source election with a
  closed-list basis (DOCTRINE.md § Source election); `basis: none` means the dependent figure is
  withheld with a data request, and the tie-out says the figure could not be established.

Never manufacture agreement: no plug, no scaling, no absorbing a residual into the
largest item.

## 5. Files

- `checks/<check>.md` — the tie-out roster: each tie's definition, sides, difference,
  resolution trail, status, elections and carry-forwards. This is the record a reviewer
  re-performs from.
- `out/tabs/<check>.xlsx` — your tab, one sheet, blocks per `WORKBOOK.md` § 4, with the
  tie-out schedule (side, source, amount, difference, status) as the primary table, the
  failure analysis where one exists, and the carry-forwards. Figures follow
  `EVIDENCE.md` § 4: every cell carries its computed value, every number in tab text
  interpolated from your ledger, never typed.

Stage, gate and rename per `WORKBOOK.md` § 8.

## `mode: fix`

Read the review record at `findings_from` and address **only the findings naming your
check** — all of them, advisory included. For each, record in your step record what you
changed and which finding it answers. A finding you disagree with is not silently ignored:
say so in `notes` with your reasoning.

A finding that needs an explanation your check's sources do not carry — an unexplained
residual, an unsupported cause, a question the reader would put to management — is
searched for in the data room before it is given up. Start where the index points — the
`relevant: "context"` entries, whose `why` says what each covers, and anything the
review's `fix_input` names — but the index does not bound you: open any file under the
run's source paths (`run.json.sources`), set-aside and unindexed files included, wherever
your judgment says the answer may sit. What you find is cited (EVIDENCE.md § 1) at the
standing its file carries — management narrative buys `candidate` with
attribution, never `supported` — and a file the index never recorded lands in your
`consumed` like any other read. A finding you cannot fix from the data room routes to
an open item — say what would be needed. Rewrite your own files only.

**Verify your own fix by diff.** Before the re-run,
read your check's current record, ledgers and tab so you hold the prior values. After,
diff the new files against them and confirm both directions: **the change is localized**
— every figure that moved is one your findings explain; a moved figure no finding
accounts for is not verified, so stop and work out why before you record — and **each
defect is corrected**, the new value or sentence showing it gone rather than merely
different. Record the diff in your step record under `fix`: per finding, what moved
(old -> new) and one line confirming the correction, plus either "nothing else moved" or
what else moved and why. This verification closes the finding — no re-review is
dispatched to validate a fix.

## Record

Write `steps/<NNNN>-tie.json` per `RUN_CONTRACT.md`: `check_id` set, `produced` naming
your files,
`consumed` listing every file you opened with its mtime, `blockers` for anything you could
not reach. `conclusion` names what tied and what did not, with the worst difference in
dollars, in two sentences. Return at most ten lines.
