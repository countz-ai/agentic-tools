---
name: check-extract
description: >-
  Perform one extraction: parse the data-room files the plan's steps read into the run's
  typed cache, once, with every file's header, columns, row count and control total
  recorded in the cache manifest for the steps that read it to cite from.
context: fork
agent: countz-accounting:worker
background: false
user-invocable: false
---

# Perform one extraction

Arguments: `run_dir`, `seq`, `check` (the step id), `sources` (comma-joined source ids —
the sources the files sit under), `goal`, `params` (`files`, the list to parse — the
spec is the docstring of `${CLAUDE_PLUGIN_ROOT}/scripts/extract.py`), `mode` (`fresh` |
`fix`), and on `fix`, `findings_from`.

This step computes no figure and writes no tab. It runs one script and records what
the script wrote. Read `${CLAUDE_PLUGIN_ROOT}/reference/CONDUCT.md` (§ Files, § Events)
and nothing else; open no client file yourself — the script reads them, bounded to the
files the plan named.

## 1. Extract

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract.py <run_dir> --step <check>
```

It reads `params.files` from the run's definition, writes `cache/<id>.parquet` per file
and `cache/manifest.json`, and prints one line per file — id, rows, the control total
and its column, the header row, every column with its dtype — then `FAILED: <id> —
<reason>` for any file it could not parse. Exit 0 means every file landed.

## 2. Read what it printed, once

Against the plan's profile of each file (`sources/<id>.md`, where the planner wrote one):
a header row other than the profile's anchor, a column typed `String` the profile calls
an amount, a control total the profile did not expect. A wrong header or type is fixed
in the definition's `params.files` (`header_row`, `types`, `control`) — never by editing
a cached file — and the script re-run. A row count that differs from the plan's is a
note: the plan counted lines, the script counts rows.

The manifest's `header_row` is the spec's, and the spec's is the profile's anchor, so a
manifest that matches the profile proves nothing about the file. The script's own check
of the header is the `HEADER:` line below; a note that the header rows match the
profile is not written.

Five more lines the script prints, and what each is to you:

- `HEADER: <id> — read at line N as the spec gives it; <why>` — the row read as the
  header may be a data row or a preamble line: the file's own layout puts the header
  elsewhere, or header names are values. Open the file's first lines and rule. A wrong
  anchor is fixed in `header_row` (or dropped, so the script detects it) and the script
  re-run. An anchor that is right is noted, and the note quotes the header line and the
  line its run starts on. A `HEADER:` line you cannot rule on is a blocker.

- `TRAILING: <id> — lines N..M below the block` — records the script did not read. A
  second table the plan anchored is its own entry, with `header_row` and `rows`, added
  to `params.files` and the script re-run; a total row or a footer the profile names as
  such is noted in the record. Lines the profile does not account for are a blocker
  naming the id and the line range.
- `SUSPECT: <id> row N (line L) — <reason>` — a row inside the block that may not be
  data: a repeated header, a total or subtotal row, text in an amount column. Rule on
  each against the profile: a row that is not data is cut with `rows` as ranges
  (`"6:40,42:1204"`) and the script re-run; a row that is data is noted with why. A
  suspect you cannot rule on is a blocker.
- `AGREES:` / `DISAGREES: <id> — <cache total> vs <the plan's citation> <its total>` —
  the block's control column summed against the planner's own whole-block read of the
  file. A disagreement exits 1 and is a blocker until the block is corrected (a wrong
  header row, a total row inside it, a block cut short) or the profile citation is
  shown wrong, which you record and the plan owns.
- `OVERRIDDEN: <id> — {...}` — the entry was read with `cache/overrides.json` applied
  over the definition's spec (`mode: fix` below).

## 3. Files

- `checks/<check>.md` — one table, one row per file in `params.files`: id, file (the
  manifest's `file`), rows, control column and total, header row, `landed` or the
  `FAILED` line. Then the notes of § 2. No figures ledger, no evidence ledger: the
  manifest is the record every consumer cites from
  (`${CLAUDE_PLUGIN_ROOT}/reference/EVIDENCE.md` § 1).

A file that failed is a blocker naming its id and the reason, and the step ends
`outcome: blocked` when any file failed — the steps that read that id fall back to the
source file (`agents/worker.md` § Your procedure). Never drop a file from `params.files`
to make the step pass.

## `mode: fix`

`fix_input` carries the `cache_defects` a reading step recorded (`RUN_CONTRACT.md` § The
step record): per id, what was wrong and the spec keys that correct it. Apply each as
an override and re-run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract.py <run_dir> --step <check> --override '{"<id>": {"rows": "6:40,42:1204"}}'
```

The override lands in `cache/overrides.json` and applies on every later run; the
definition is not edited. Read § 2 again on what the re-run prints. Rewrite only
`checks/<check>.md`, adding a row per override: id, the defect, the keys applied, and
the control total before and after. Record under `fix` per defect what moved.

## Record

Write `steps/<NNNN>-extract.json` per `RUN_CONTRACT.md`: `check_id` set, `produced`
naming `cache/manifest.json`, every `cache/<id>.parquet` and `checks/<check>.md`,
`consumed` every file the manifest names with its mtime, `blockers` one per failed file.
`conclusion` counts the files cached and names each that failed, in two sentences.
Return at most ten lines.
