---
name: check-review
description: >-
  Adversarially review the run's checks: run the mechanical gates, then the bounded
  validation scope in VALIDATION.md — footing, re-performance, sampling, prose,
  boundary, empty results, the objective, each kind's own procedure — against the user's
  own files, and write findings. Never edits the work.
context: fork
agent: countz-accounting:critic
background: false
user-invocable: false
---

# Review the checks

Arguments: `run_dir`, `seq`, `checks` (comma-joined check ids to review), and optionally
`carry_from` (a prior review record whose findings on checks outside this list are
carried forward). The `checks` list narrows the surface, not the standard — each named
check gets the full scope.

## What to read

1. `${CLAUDE_PLUGIN_ROOT}/reference/VALIDATION.md` — the scope you run and the finding
   you write. Read it whole; it is the only file that states the scope.
2. `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` — the standard behind every `judgment`
   finding
3. on a plan-driven run, the recipe at `run.json.plan.recipe` — its population rule is
   what the boundary test reads — and `PLAYBOOK_RECIPES.md` § What every recipe inherits
4. for each check under review: its `checks/<check>.md` record (match table included),
   its `workpapers/` ledgers, and its tab in `out/tabs/`; after a report has landed, the
   assembled workbook and report deck with its source, `out/report.yaml`

## Order

`VALIDATION.md § Prose checking` first, then `VALIDATION.md § The validation scope` in
the order it numbers. Run the scope over every check the `checks` argument names.

## Findings

Shape, severity, routing and the `check:` vocabulary per `VALIDATION.md § Findings`;
grade by consequence; an advisory finding never gets `fix_kind: rerun_check`;
`rerun_check` requires `fix_check`.

Before routing a finding `data_request` or `management_question`, look for the answer in
the data room itself — it often already holds management's commentary, board materials, or a
neighboring schedule. Start from `file_index.json`'s context entries
(`relevant: "context"`), and go past it to any file under the run's
source paths (`run.json.sources`) per your judgement, set-aside and unindexed files
included. Where a file plausibly answers the question, route `rerun_check` instead, with
`fix_input` naming the file and what to look for.

A review dispatch is always the start of a round — one round of critique-fix is a review
plus the fix re-runs its findings buy, each fix verifying its own change by diff. **You
are never dispatched to validate a fix.** On a later round: restate a finding whose fix
recorded a verified diff as `disposition: "fixed"` without re-performing it, and apply
the one-attempt rule (`VALIDATION.md § Routing`). Copy each `carry_from` finding on a
check you did not re-perform into your record verbatim with `carried: true` — your
record's `findings[]` is the complete current set, and a finding you drop silently
vanishes from the open-item accounting.

## Record

Write `steps/<NNNN>-review.json` per `RUN_CONTRACT.md` § The step record, with
`findings[]` populated. `conclusion` gives counts by severity and the worst finding in
one clause. Return at most ten lines; the findings live in the record.
