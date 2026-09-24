---
name: check-extract
description: >-
  Perform one extraction: write and run the script that parses every table the plan's
  steps read out of the data room into the run's typed cache, once, with each table's
  file coordinates, column parses, row count and control total recorded in the cache
  manifest for the steps that read it to cite from.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one extraction

Arguments: `run_dir`, `seq`, `check` (the step id), `sources` (comma-joined source ids —
the sources the files sit under), `goal`, `params`, `mode` (`fresh` | `fix`), and on
`fix`, `fix_input`. On a saved playbook's run, `params.prior_script` names last period's
script for this step, relative to the playbook file (`run.json.playbook.path`).

`params.files` lists the tables to parse, one entry per table a step reads: `{id, path,
source?, file_role, sheet?, what?, control?}` — `path` relative to the source, `what` the
table in the planner's words (`"the By-stream table, header at row 40"`), `control` the
column a check agrees a total to, or `"none"`. How each table is written — header,
rows, types, dates, signs — is yours to find and state.

This step computes no figure and writes no tab. Read
`${CLAUDE_PLUGIN_ROOT}/reference/CONDUCT.md` (§ Files, § Events), the planner's profile
of each file (`sources/<source>.md`), and the docstring of
`${CLAUDE_PLUGIN_ROOT}/scripts/cache.py`.

## 1. Look

`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/peek.py <path>`
on each file, then bounded reads in code of only what you need to write the parse: where
each table's header and last row sit, what lies between and below, how amounts, dates
and signs are written.

## 2. Write the script

`workpapers/extract-<check>.py`, with polars, openpyxl, fastexcel or pypdf as the file
needs. Where `params.prior_script` is set, read it first and start from it, changing
what this period's files show is different; never run it unread. Per `params.files`
entry, parse that table and `cache.write` it — with the entry's `what` — and true file
coordinates (`header_at`, `rows` as the rows sit in the file) and, per column, where it
sits and how its text was read (`parse`, in words). A value you cannot read stays text,
and its column's `parse` says so. Where the document states a total for the table, pass
it as `stated`. Any other table you see on a file is a `cache.note`, not extracted.

The script is the run's record of how every file was read: a reviewer re-performing a
citation reads the file as it says, and a fix pass edits it. Write it to be read.

## 3. Run and rule

`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 workpapers/extract-<check>.py`, then
`cache.py <run_dir> --show`. A `stated` total the rows do not agree to, or a row count or
control total that disagrees with the profile's citation of the same table, is a
blocker until you explain it — correct the script and re-run, or rule on why the
difference is right and record the ruling. A table you could not parse is a blocker
naming its id; never drop an entry to make the step pass.

## 4. Files

`checks/<check>.md` — one table, one row per id: file, rows, row count, control total,
stated agreement. Then the manifest's `not_extracted` notes, then your rulings. No
figures or evidence ledger: the manifest is what consumers cite
(`${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md` § 1).

## `mode: fix`

`fix_input` carries the `cache_defects` reading steps recorded: `{id, what, fix}`, `fix`
in words. Edit the script to do what each `fix` says, re-run it, and § 3 again. Add a
row per id to `checks/<check>.md`: the defect, what the script now does, the control
total before and after. Record under `fix` per defect what moved.

## Record

Write `steps/<NNNN>-extract.json` per `RUN_CONTRACT.md`: `check_id` set, `produced`
naming `cache/manifest.json`, every `cache/<id>.parquet`, `workpapers/extract-<check>.py`
and `checks/<check>.md`; `consumed` every file the manifest names with its mtime;
`blockers` one per unparsed table or unexplained disagreement. `conclusion` counts the
tables cached and names each that did not land, in two sentences. Return at most ten
lines.
