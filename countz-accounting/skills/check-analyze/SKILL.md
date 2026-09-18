---
name: check-analyze
description: >-
  Perform one analysis: execute a declared analytical procedure — a breakdown, a
  classification walk, a composed schedule — over validated inputs, with every member
  of the stated population ruled against its evidence and every figure computed by
  code, fully re-performable.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one analysis

Arguments: `run_dir`, `seq`, `check` (the check id), `sources` (comma-joined source ids),
`goal` (the stated goal, or `(none)`), `params`, `mode` (`fresh` | `fix`), and on `fix`,
`findings_from`.

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` (§ Working with
numbers, § Resolving issues, § Voice), `${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md`,
then `sources/<id>.md` for each of your sources, where it exists — a plan-driven run's
planner writes the profiles; derive a binding yourself where none answers it.

## 0. Resolve the procedure

What this analysis does comes from its declaration. Resolve it, first match wins:

- `params.family` set — a plan-driven step: the family section is your procedure
  (`agents/worker.md` § Your procedure).
- otherwise — the `goal` is the procedure, in the user's words.
- neither — record the step blocked; an analysis with no declared procedure is not run.

## 1. Define the analysis

State before computing anything: the question, the population tested, the period and
grain, and the schedules this check will emit. Where the procedure rules on members,
state also the closed ruling vocabulary in force and the declared options that steer it
(`params`, e.g. a declared `perspective`). An option the user did not declare is never
assumed.

## 2. Compute

Per DOCTRINE.md: code computes every figure, at full precision, from the sources and
the declared dependency reads — you transcribe nothing. One citation per read in
`workpapers/evidence-<check>.yaml`; every number that may reach the deliverable as a
figure in `workpapers/figures-<check>.yaml`, populations stated with exclusions named.
Item-grain work lands as `checks/<check>-<table>.csv` tables with their manifest blocks
per EVIDENCE.md § 5. No size threshold narrows the computation: every member of the
stated population enters the schedules at full precision, whatever its amount
(DOCTRINE.md § Materiality).

## 3. Rule

Where the procedure classifies members — accounts, cost lines, adjustment candidates:

- **every member of the stated population is ruled** from the closed vocabulary, and
  the record names the basis even when the ruling is "no change". A member left unruled
  is recorded as a coverage gap.
- **every ruling cites its evidence at the standing the evidence carries**:
  system-of-record reads support a measured figure; management-prepared support buys
  `as_stated` or candidate standing with attribution, never more. A ruling the sources
  cannot support is recorded as a candidate naming what would substantiate it, with the
  `D.` or `Q.` open item that asks for it.
- a ruling that moves an amount states the arithmetic in the figure's `expression`.
- where two sources disagree under the analysis, elect one per DOCTRINE.md § Source
  election; `basis: none` withholds the dependent figure with a data request.

## 4. Files

- `checks/<check>.md` — the definition, the procedure as resolved, each schedule, every
  ruling with its basis, the exceptions and the open items.
- `checks/<check>-<table>.csv` — the item-grain tables of § 2, each with its manifest
  block.
- `out/tabs/<check>.xlsx` — your tab, blocks per `WORKBOOK.md` § 4, with the schedules as
  the primary table, the rulings and their bases, and the exceptions.

Close `checks/<check>.md` with the answer: whether every member was ruled and every
schedule footed. Then the members left unruled, the schedules that do not foot, the
limitations the reader must weigh — a degraded grain, candidates standing on
management-prepared support — and any figure the analysis could not establish.

Stage, gate and rename per `WORKBOOK.md` § 8.

## `mode: fix`

Exactly as `check-tie`: address every finding naming your check, record what changed and
what you disagree with, rewrite only your own files — the item tables included.

## Record

Write `steps/<NNNN>-analyze.json` per `RUN_CONTRACT.md`: `check_id` set, `produced`
naming your files, `consumed` every file you opened with its mtime, `blockers` for
anything you could not reach. `conclusion` names what the analysis established and the
largest open matter, in two sentences. Return at most ten lines.
