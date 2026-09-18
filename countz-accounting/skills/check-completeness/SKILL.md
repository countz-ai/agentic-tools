---
name: check-completeness
description: >-
  Perform one completeness check: agree two or more rosters of the same population — GL
  cash accounts against bank accounts evidenced by statements, a listing against a
  ledger — in both directions, with every unmatched member an exception.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one completeness check

Arguments: `run_dir`, `seq`, `check` (the check id), `sources` (comma-joined source ids —
the first carries the subject roster, the rest the evidencing rosters), `goal` (the
stated goal, or `(none)`), `params`, `mode` (`fresh` | `fix`), and on `fix`,
`findings_from`.

Read, in this order: `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` (§ Voice),
`${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md` (§ 3 for the population fields, § 5 for
the table), then `sources/<id>.md` and `sources/<id>.entities.json` for each source,
where they exist — a plan-driven run's planner writes them; build the rosters from the
sources themselves where they do not.

## 1. Define the population

State before building anything: the population (bank accounts, GL accounts, statement
sets), the member grain, the period, and what counts as evidence of membership on each
side. A completeness check asserts the same population appears whole in every roster; it
compares membership, never amounts — an amount difference on a matched member belongs to
a tie-out or reconciliation, and you note it in `blockers` for routing rather than
judging it here.

## 2. Build each roster

Each roster from its own source, every member with a citation in
`workpapers/evidence-<check>.yaml`; member counts per roster as figures in
`workpapers/figures-<check>.yaml`. The subject roster is the population the plan drew
or, where `params.roster_from` names a check, that check's recorded population at its
recorded members (the step is `after` it) — never a label filter over the source. A
member the source carries that the population rule could cover and the roster omits is
reported in `blockers`, not dropped.

## 3. Match members, in passes

By identifier first (account number or masked suffix), then by name or label, then by
corroborating facts (a balance and period that agree), each pass recorded, a loose-key
match stating its key. Write `checks/<check>-roster.csv` — member, presence per source,
match key, classification, exception id where one is minted — with its manifest block in
`checks/<check>.md` per EVIDENCE.md § 5. The roster accounting must close in both
directions: matched plus explained absences plus exceptions equals each roster's count.

## 4. Classify every member

`matched` | `explained_absence` (opened or closed inside the period, with that event's
own evidence) | exception. Every unmatched member is an `X.` exception naming the side it
is missing from, the member, its balance where one side states it, what would clear it,
and who owns that. Never resolve a missing member by assuming the rosters were meant to
differ.

## 5. Files

- `checks/<check>.md` — the definition, the rosters, the passes, the classifications and
  the exceptions.
- `checks/<check>-roster.csv` — the roster table of § 3, with its manifest block.
- `out/tabs/<check>.xlsx` — your tab, blocks per `WORKBOOK.md` § 4, with the roster
  schedule as the primary table and the exceptions.

Close `checks/<check>.md` with the answer: whether both rosters are whole in both
directions. Then the absences, the ones you explained separated from the ones still
standing, and any roster that could not be built from its source.

Stage, gate and rename per `WORKBOOK.md` § 8.

## `mode: fix`

Exactly as `check-tie`: address every finding naming your check, record what changed and
what you disagree with, rewrite only your own files — the roster table included.

## Record

Write `steps/<NNNN>-completeness.json` per `RUN_CONTRACT.md`: `check_id`, `produced`,
`consumed` with mtimes, `blockers`. `conclusion` states the roster sizes and
the exception count in two sentences. Return at most ten lines.
