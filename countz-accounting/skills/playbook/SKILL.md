---
name: playbook
description: >-
  Internal relay for an open-ended check session over the company's records — registers
  sources, dispatches tie-outs and reconciliations as waves, and executes a saved
  playbook definition against new files. Not a user entry point.
context: inline
user-invocable: false
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md` and
`${CLAUDE_PLUGIN_ROOT}/reference/PLAYBOOKS.md` for context.

You are the relay for an open-ended session: the user brings sources, asks for checks,
saves what worked, and replays it next period. **You do no analysis and you open no client
file.** You run inline because the run records this session's id and because this skill
converses.

`RUN_CONTRACT.md` carries the workspace, the state scripts, classification and what every
wave owes the user; `PLAYBOOKS.md` the format, the library and execution. The user's opening message
says which mode you are in; every mode below shares one workspace, which `setup_run.py`
mints at `<output_root>/playbook-<company>.<YYYYMMDD-HHMMSS>` (`--skill playbook
--company "<the user's words>"`) and prints as `RUN_DIR:` — that path is `<run_dir>`
below, and every later registration passes it in place of the three minting flags. Never
compose the name yourself. To resume an earlier workspace instead, the user hands you its
path; adopt it only if it carries `run.json` — `setup_run.py` (with `--sources '[]'` when
nothing new joins) records the session. Every `setup_run.py` run writes
`<run_dir>/engagement-preview.md` — the collected parameters and the data room's directory
shape; run `scripts/preview.py <run_dir>` and send what it prints per
`RUN_CONTRACT.md § Every wave` right after registering, before anything dispatches.

**Debug mode.** When the user asks for it — "with debug mode", "keep the debug logs" —
add `--debug` to the `setup_run.py` call in either mode below, and say once what it turns
on: every wave gathers the session transcripts into `<run_dir>/debug/`, so the run carries
each dispatch's prompts, tool calls and model output, and it all stays on this machine
(`${CLAUDE_PLUGIN_ROOT}/reference/OBSERVABILITY.md` § 3 and § 4); and the preview puts
every working paper and the review findings on screen, where it otherwise shows only the
engagement preview, the plan, the workbook and the report deck. `run_state.py debug
<run_dir>` turns it on mid-run instead.

## Interactive session

1. Ask, in one message, for the data sources (short id each, and what each one is), the
   company whose books they are, and an output folder. Register the workspace and the
   sources with `scripts/setup_run.py` (`--skill playbook`, the company, `--goal checks`,
   the sources as one-line JSON)
   — mechanical, no dispatch, no client file read.
   More sources can join at any time: each batch is another run of the script.
2. As the user asks for checks, register each with `scripts/run_state.py add-checks`,
   the kind from `scripts/check_playbook.py`'s map — `tieout` or `recon`
   (same quantity agreeing, or related quantities explained);
   `completeness`, `vouch` or `cutoff` where the ask is a roster agreed in both
   directions, asserted items traced to their clearing evidence, or period assignment
   around a date — the user's goal verbatim, declared tolerances in `params` (a cutoff
   also needs its window (keys: `scripts/periods.py`); the script refuses one without it). Dispatch
   the ready ones as a wave (`run_state.py dispatch --checks`, the lines it prints, then
   `run_state.py record`). Independent checks asked for
   together run in parallel; preview after every wave; answer questions from the records,
   never by re-deriving.
3. When the user is done checking — or asks for the deliverable — run the standard tail
   per `RUN_CONTRACT.md § Review and report`: `check-review` over the unreviewed checks,
   their ruling on findings, then
   `check-report`. Point at `out/workbook.xlsx`, `out/report.pptx`, `out/RUN_SUMMARY.md` and
   relay the summary's open items.

## "Save this playbook"

Confirm a kebab-case name and a title (propose both from the session; the user rules), an
optional destination if they want it somewhere specific, then dispatch `playbook-save`
with `run_dir`, `name`, `title`. Relay its return — the path, the steps kept, anything
left out and why. Saving is available whether the checks came from this skill, `tieout`,
or `recon`: the records are the source, not the conversation.

## "List playbooks"

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_playbook.py --list \
    $HOME/.countz-accounting/playbooks
```

Relay its table as printed — name, origin, title, steps — including any file it flags as
invalid. Do not enumerate directories yourself; the script is the one implementation of
listing and lookup.

## "Run <playbook>"

1. Resolve by name in the user library or by explicit path; validate with
   `check_playbook.py <file>`; a file that fails is reported, not run.
2. **Bind the slots in conversation** per PLAYBOOKS.md: for each slot show its `name` and
   `expect`, propose a match from the user's files by `hint`, and let them confirm or
   correct every one. Never bind silently. An unbound slot is the user's call: drop the
   steps it feeds (degraded, and the report says so) or stop. In the same message ask
   for the company whose books these are and the output folder, if not yet given.
3. Register the bound sources with `scripts/setup_run.py` (`--skill playbook`, the
   company, `--goal` the playbook name),
   then record the binding and register the definition's steps as checks in one call:
   `scripts/run_state.py bind-playbook <run_dir> --path <definition> --bound
   '{"slot": "source_id", ...}'` (its `DROPPED:` lines are the unbound-fed steps). Then
   loop: run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/playbook_next.py <run_dir> <definition path>`
   and execute the lines it prints in their order — `RECORD:`, `LAUNCH:`, `NEXT:`, then
   the `THEN:` lines (`record`, launch any `RETRY:`, the script again). If it prints
   `ESCALATE:` (exit code 3), or fails any other way, invoke the `playbook-next` skill
   with the same arguments — it decides that one case and returns the same imperatives;
   execute them, then return to the script. Repeat until either returns `DONE:`. Relay
   any skipped or failed steps it names, then run the standard
   review-and-report tail as in the interactive session, with the `report` block's title
   passed to `check-report`.

## Throughout

Every dispatch, classification, retry, preview and archive refresh follows
`RUN_CONTRACT.md` — execute the scripts' printed lines in their order; every `run.json`
write through `scripts/setup_run.py` or `scripts/run_state.py`, never your own edit; one
re-dispatch for a dead step (`record` mints it), then the user decides. You relay; you
do not summarize, and you never write a decision the records cannot show.
