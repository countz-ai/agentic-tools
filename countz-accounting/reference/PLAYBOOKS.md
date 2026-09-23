# PLAYBOOKS — saved check sequences: the format, the library, and how one executes

A playbook declares named source **slots**, the **steps** to run over them, and the
report's title. It carries no paths and no figures, so the same playbook runs against
next period's files unchanged. A playbook has one of two origins:

- **saved**: `playbook-save` distilled a session's executed checks into a file. This is
  the normal origin.
- **planned**: `check-plan` drafted it inside a run, from the data room against a
  playbook recipe (served by the Countz connector or generated for the run, pinned at
  `<run_dir>/recipes/<name>.md` — `RECIPE_FORMAT.md`). It lives at
  `<run_dir>/plan/<name>.json`, its slots are the run's own source ids, and once the user
  approves the plan it executes like the other two. The recipe's shim skill owns when a
  plan runs; `scripts/run_state.py approve-plan` records the approval.

## The file

One JSON file per playbook, named `<name>.json`; the file stem and `name` must match.

```json
{
  "schema": "countz-accounting/playbook@1",
  "name": "month-end-close",
  "title": "Month-end close checks",
  "description": "one line, shown by the list",
  "saved_at": "<ISO 8601 UTC>",
  "created_from": "<run_id of the run it was distilled from, or null>",
  "sources": [
    {"slot": "gl",
     "name": "General ledger detail",
     "expect": "one row per posting: account, date, amount, reference",
     "hint": "*gl*|*general*ledger*"}
  ],
  "steps": [
    {"id": "tie_gl_tb",
     "check": "tieout",
     "sources": ["gl", "tb"],
     "goal": "<what this check establishes, in the user's words>",
     "params": {},
     "after": []}
  ],
  "report": {"title": "Month-end close checks"}
}
```

`scripts/check_playbook.py <file>` validates a file; this document explains the fields.
`name`, slot ids and step ids are lower-case slugs (`[a-z0-9][a-z0-9_-]*`). `sources`
and `steps` are non-empty; every slot is referenced by at least one step; every step names
at least one slot.

- `sources[].slot`: the id steps reference. `name` (required) and `expect` are what the
  binding conversation shows the user. `hint` is a filename glob, alternatives split by
  `|`, used only to propose a match, never to bind silently.
- `steps[].check`: a check kind. The kind-to-skill map is `KINDS` in
  `scripts/check_playbook.py`. Adding a kind means adding a worker skill (its procedure
  and its item tables), a `KINDS` row and, where the kind requires params, a `PARAMS`
  row, in the same change. One kind computes no figure: `extract` parses the data-room
  files the other steps read into `<run_dir>/cache/`, once, ahead of them
  (`scripts/extract.py`; the file table in `RUN_CONTRACT.md`). Its `params.files` lists the
  blocks — id, path under a slot, header row and data rows, types and control column,
  per the script's docstring; a file stacking several tables is several entries — and
  it names no `_from`. A step that reads the cache carries
  `params.cache_from` (the extract step) and `params.reads` (the ids it reads);
  `check_playbook.py` refuses a read of an id the extract step does not parse. A file
  the extract step could not parse is read from the source by the steps that name it.
- `steps[].goal`: carried verbatim into the check dispatch. A step with no goal runs the
  kind's default procedure.
- `steps[].params`: options the check must honor: declared tolerances, a cutoff's
  `period_end` and `window_days`, `items_from` naming the step whose record supplies the
  item list. `PARAMS` in `scripts/check_playbook.py` states which keys a kind requires;
  each kind's SKILL.md states what the keys mean. Every key ending `_from` names a step
  in the step's `after`, or several.
  A plan-driven step also carries `family`, the recipe family it performs, and
  `entities`, the entities it covers — most steps cover several, and the worker performs
  the family once per entity inside the one check (`agents/worker.md` § Your procedure).
  A family planned as more than four steps carries `split_reason` on each, the measured
  fact that split it; `check_playbook.py` refuses the definition otherwise, because a
  family fanned out one entity per step makes every worker re-establish the same binding
  and scatters one family's work over a tab each.
- `steps[].after`: step ids that must be terminal first. Steps whose `after` is
  satisfied run together as one wave. `after` is **derived from the step's reads**: it
  is exactly the set of steps the step's `_from` params name (`items_from`,
  `cache_from`, `cube_from` and the like), and `check_playbook.py` refuses an `after`
  entry no `_from` reads as much as a `_from` naming a step outside `after`. A step
  reads the records and check files of the steps it names and no other. The recipe
  declares what a family reads from another; the plan, which knows the data room,
  derives the order — a recipe never states one. No self-dependency, no cycle.
- `report`: the deliverable's title. The title names the work (`Month-end close checks`) and neither the
  company nor the period; the run carries both and the deck's cover prints them beside
  the title (`REPORT.md` § 2). `check_playbook.py` refuses a period token in `title` or
  `report.title`. Review and report are not steps: every playbook run ends with the
  review-then-report tail from `RUN_CONTRACT.md`.

## The library

| where | holds | written by |
|---|---|---|
| `$HOME/.countz-accounting/playbooks/` | the user's saved playbooks | `playbook-save` |

Listing and lookup come from one implementation:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_playbook.py --list \
    $HOME/.countz-accounting/playbooks
```

It prints one line per playbook (name, origin dir, title, step count, kinds) and flags a
file that fails validation. Resolution by name searches the user's library. Running
from an explicit path bypasses the library. The user may save to a
path of their choosing; the library is the default.

## Saving

`playbook-save` distills `run.json`, never the conversation:

- Every executed check becomes a step: kind, `goal` verbatim, `params` as dispatched. A
  check that failed is left out, and the return says so.
- Every source a kept step references becomes a slot: the run's source id becomes the
  slot, `name` from the source entry, `expect` from the executed definition's slot where
  one exists and otherwise from what the kept checks recorded the source to hold, `hint`
  from its filename.
- `after` is copied from the definition the run executed (`run.json.playbook`) where one
  exists, with edges to left-out steps removed. An interactive session's checks had no
  sequencing and get `after: []`; the user adds sequencing by adding a `_from` read to
  a step's `params` and the step it names to `after`.
- Nothing is invented. A playbook contains only steps that ran.

Validate before returning: `check_playbook.py <file>` must exit 0, or the save reports
the error and leaves no file in the library.

## Running

1. **Resolve** the playbook by name or path and validate it. A file that fails
   validation is reported, not run.
2. **Bind** every slot, in conversation: propose a match from the user's files by
   `hint`, show `name` and `expect` for each slot, and let the user confirm or correct.
   A slot with no file is a gap: the user drops the steps it feeds (the run continues
   degraded, and the report says so) or stops. Never guess a binding the user has not
   seen.
3. **Execute**: register newly bound sources with `scripts/setup_run.py`, record the
   binding and the steps as checks with `scripts/run_state.py bind-playbook`, then run
   check waves as the playbook engine names them: `scripts/playbook_next.py` first,
   always, and the `playbook-next` skill when it prints `ESCALATE:` or fails. Either
   reads the definition and the step records, emits one wave per decision with its
   briefs, and reports `DONE:` when every step is terminal. Then the review-then-report
   tail. The relay classifies and records as in `RUN_CONTRACT.md`; a playbook run differs
   only in where the roster comes from.
