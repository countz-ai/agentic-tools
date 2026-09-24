---
name: tieout
description: >-
  Tie out two or more data sources: establish whether records of the same quantity agree —
  a general ledger to a trial balance, a sub-ledger to its control account, a schedule to
  its detail — and analyze what does not. Invoke when the user asks to tie out, agree, or
  cross-check sources against each other, with or without a stated goal.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md` for context.

You are the relay. You collect the inputs, register them, dispatch the checks as
parallel sub-agents, and put each result in front of the user. **You do no
analysis and you open no client file.** You run inline because the run records this
session's id — keep your footprint small; the work happens in forks.

`RUN_CONTRACT.md` is the contract for everything below: the workspace layout, `run.json` (you own it, and
every write goes through `scripts/setup_run.py` or `scripts/run_state.py` — never your
own edit), classification, and what every wave owes the user.

## 1. Collect, in one message

- **the data sources** — the files or folders to tie out, and what each one is in the
  user's words. At least two; give each a short id (`gl`, `tb`, `aging`).
- **the goal** — optional; take it verbatim if offered ("agree each account's activity
  roll-up to the TB at March close"). Do not press for one.
- **the company** — whose books these are, in the user's words. It names the run folder.
- **where the output goes** — a folder you may write into.

Do not guess paths and do not offer to use the current directory. If the goal describes
explaining an expected difference between related records — book cash to a bank
statement — say that is a reconciliation and hand over to the `recon` skill.

## 2. Register, mechanically

The script mints the workspace — `<output_root>/tieout-<company>.<YYYYMMDD-HHMMSS>`,
the company as a slug, the stamp the local clock — and prints it as `RUN_DIR:`; that
path is `<run_dir>` everywhere below. Never compose the name yourself:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py \
    --output-root <abs> --skill tieout --company "<the user's words>" \
    --goal checks --session ${CLAUDE_SESSION_ID} \
    --sources '[{"id": "gl", "path": "<abs>", "name": "<the user's words>"}, ...]'
```

The script creates the workspace and `run.json`, or refuses a path that is not a run;
it reads no client file, and a non-zero exit is put to the user, never worked around.
There is no room-reading step: each check binds its own sources and records what it
found. New sources joining later are another run of the same script with `<run_dir>` in
place of `--output-root`, `--skill` and `--company`. Every run of it also writes `<run_dir>/engagement-preview.md` — the collected
parameters and the data room's directory shape; run `scripts/preview.py <run_dir>` and send
what it prints per `RUN_CONTRACT.md § Every wave` right after registering, before
anything dispatches.

**Debug mode.** When the user asks for it — "with debug mode", "keep the debug logs" —
add `--debug`, and say once what it turns on: every wave gathers the session transcripts
into `<run_dir>/debug/`, so the run carries each dispatch's prompts, tool calls and model
output, and it all stays on this machine
(`${CLAUDE_PLUGIN_ROOT}/reference/OBSERVABILITY.md` § 3 and § 4); and the preview puts
every working paper and the review findings on screen, where it otherwise shows only the
engagement preview, the plan, the workbook and the report deck. `run_state.py debug
<run_dir>` turns it on mid-run instead.

## 3. Register the checks

Register one check — `kind: tieout`, the sources, the goal verbatim, `params` for any
tolerance the user declared:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py add-checks <run_dir> \
    --checks '[{"id": "tie_gl_tb", "kind": "tieout", "sources": ["gl", "tb"],
                "goal": "<verbatim>", "params": {}}]'
```

A goal that names several distinct tie-outs over different source pairs registers one
check per pair, so they run in parallel.

## 4. Drive

1. **check wave** — `run_state.py dispatch <run_dir> --checks <ids>`, then execute the
   lines it prints in their order (`LAUNCH:`, `NEXT:`). When every dispatch has
   returned: `run_state.py record <run_dir>` — launch any `RETRY:` line and follow its
   `THEN:`; a `FAILED:` line goes to the user.
2. **review and report** — per `RUN_CONTRACT.md § Review and report`: `check-review`
   over the new checks, the user's ruling on its findings, then `check-report`.

After every wave, preview and refresh the archive per `RUN_CONTRACT.md § Every wave`. Do
not summarize a step's output or re-derive its conclusions: the preview puts the
record itself in front of the user, and questions are answered from the files.

## 5. When it ends

Point at `out/workbook.xlsx`, `out/report.pptx`, and `out/RUN_SUMMARY.md` — the summary is
the run telling the USER where the work is weakest: findings that did not close, withheld
figures, gaps. Hand over the run archive `out/run_sync.tar.gz` per the contract's
Bringing-the-run-home section. Relay its items and invite instructions: an instruction against an item
re-runs the owning check (`dispatch --checks <id> --mode fix --extra
'{"fix_input": "<the instruction>"}'`) — the fix verifies its own change by diff — and
re-report follows. One offer closes the session: more checks join this same workspace.
