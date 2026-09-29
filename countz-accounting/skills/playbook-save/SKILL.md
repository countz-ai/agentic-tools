---
name: playbook-save
description: >-
  Distill a session's executed checks into a saved playbook file the user can replay
  against next period's files. Distills the records, never the conversation.
context: fork
agent: countz-accounting:playbook-engine
background: false
user-invocable: false
---

# Save a playbook

Arguments: `run_dir`, `name` (kebab-case, the user's choice), `title`, and optionally
`dest` (a directory; the default is `$HOME/.countz-accounting/playbooks/`) and
`overwrite=true` (replace an existing file of the same name).

Read `${CLAUDE_PLUGIN_ROOT}/reference/PLAYBOOKS.md` — the format and the distillation
rules — then `run.json` and, where the run executed a definition, that definition
(`run.json.playbook`).

## Distill

From `run.json`, never from anything the user said that did not become a record:

- **steps** — one per executed check: `id` from the check id, `check` from its kind,
  `sources` from its source ids, `goal` verbatim, `params` as dispatched. `after` is
  copied from the definition the run executed (`run.json.playbook`) with edges to
  left-out steps removed; checks with no definition behind them get `after: []`. A check
  whose status is `failed` is left out, and your return says so. A check the user asked
  you to leave out stays out.
- **slots** — one per source a kept step references: `slot` from the source id, `name`
  from the source entry, `expect` copied from the executed definition's slot where one
  exists — otherwise distilled from what the kept checks recorded the source to hold
  (their records and citations state the grain) — and `hint` from the filename it was
  bound to this time.
- **provenance** — `saved_at` now, `created_from` the run id.
- **extract scripts** — for each kept `extract` step, copy the run's
  `workpapers/extract-<check>.py` to `<dest>/<name>.extract/<check>.py` and set the step's
  `params.prior_script` to `<name>.extract/<check>.py`: next period's extract worker
  starts from it.
- **nothing invented** — no step that did not run, no slot nothing references, no
  sequencing the run did not have.

## Write and validate

Write `<dest>/<name>.json` (create the directory; refuse to overwrite an existing file
unless the arguments say `overwrite=true`, which replaces `<name>.extract/` too — say
which file is in the way). Then:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_playbook.py <the file>
```

A non-zero exit means you return the error and delete the file and `<name>.extract/` — a broken playbook in the
library fails at its next run, in front of the user. Append the `playbook_saved`
event (`OBSERVABILITY.md`).

## Return

Saving is not a pipeline step: it writes no step record and takes no seq — the
`playbook_saved` event and the file itself are the record. Return at most five lines: the
path, the step count and kinds, and any check left out with the reason.
