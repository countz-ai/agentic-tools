---
name: recon
description: >-
  Reconcile two or more data sources: explain the difference between related records — a
  general ledger cash account to a bank statement, a payables ledger to a supplier
  statement — through item matching and classified reconciling items. Invoke when the user
  asks to reconcile sources or explain why two records differ, with or without a stated
  goal.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md` for context.

You are the relay: collect the inputs, register them, dispatch the checks as parallel
sub-agents, surface each result. **You do no analysis and you open no client
file.** You run inline because the run records this session's id.

`RUN_CONTRACT.md` is the contract for everything below — the
workspace, `run.json` (you own it; every write goes through `scripts/setup_run.py` or
`scripts/run_state.py`), classification, and what every wave owes the user. This skill
is `tieout` with a different check kind; everything below that is
not reconciliation-specific behaves exactly as that skill describes.

## 1. Collect, in one message

- **the data sources** — at least two, with what each one is; the subject side (the
  books) first, the counterparty side (the statement) second. Short ids for each.
- **the goal** — optional, verbatim ("reconcile the operating account to the March
  statement").
- **the company** — whose books these are, in the user's words. It names the run folder.
- **where the output goes** — a folder you may write into.

Do not guess paths. If the sources are two records of the same quantity that should
simply agree — a sub-ledger to its control account — say that is a tie-out and hand over
to the `tieout` skill.

## 2. Register, mechanically

Register the workspace and sources with `scripts/setup_run.py` exactly as the `tieout`
skill states it (`--skill recon`, the company, `--goal checks`, the sources as one-line
JSON). The script mints `<output_root>/recon-<company>.<YYYYMMDD-HHMMSS>` and prints it
as `RUN_DIR:` — that path is `<run_dir>` below; never compose it yourself. It creates,
folds into an existing run named by its path, or refuses a path that is not one; it
reads no client file; each check binds its own sources.

**Debug mode.** When the user asks for it — "with debug mode", "keep the debug logs" —
add `--debug`, and say once what it turns on: every wave gathers the session transcripts
into `<run_dir>/debug/`, so the run carries each dispatch's prompts, tool calls and model
output, and it all stays on this machine
(`${CLAUDE_PLUGIN_ROOT}/reference/OBSERVABILITY.md` § 3 and § 4); and the preview puts
every working paper and the review findings on screen, where it otherwise shows only the
engagement preview, the plan, the workbook and the report deck. `run_state.py debug
<run_dir>` turns it on mid-run instead.

## 3. Register the checks

Register one check per reconciliation with `scripts/run_state.py add-checks` — `kind:
recon`, sources in subject-then-counterparty order, the goal verbatim, declared
tolerances in `params`. Several independent reconciliations (three accounts, three
statements) register as several checks and run as one parallel wave.

## 4. Drive

Exactly as the `tieout` skill states it: a `check-recon` wave (`run_state.py dispatch`
→ the lines it prints, in their order → `run_state.py record`), then review and report
per `RUN_CONTRACT.md § Review and report` — preview and archive refresh after every
wave per its `§ Every wave`. No summarizing; the records speak.

## 5. When it ends

Point at `out/workbook.xlsx`, `out/report.pptx`, `out/RUN_SUMMARY.md`; hand over the run
archive `out/run_sync.tar.gz` per the contract's Bringing-the-run-home section; relay the
summary's open items and invite instructions — a directed fix re-runs the owning check
and reseals.
Offer the one closer: more checks in this workspace.
