# RUN_CONTRACT — the run directory, its files, and how waves are dispatched

A run is one directory. It accumulates sources and checks as the user asks for them.
`scripts/setup_run.py` mints it as `<output_root>/<skill>-<company>.<YYYYMMDD-HHMMSS>`
(the launcher skill invoked, the company's name as a slug, the minting machine's local
clock) and prints the path as `RUN_DIR:`. The relay never composes that name; it
addresses every later call by the printed path. A path without `run.json` is refused.
Example: "output to results" for a `qoe` run over Demo ZS lands at
`results/qoe-demo-zs.20260904-104305`. Every launcher skill under `skills/` drives the
same workspace the same way; only where the check roster comes from differs.

This document defines the step record's shape and states what the fields of `run.json`
and the dispatch briefs mean. Their shape is enforced in `scripts/setup_run.py` and
`scripts/run_state.py`. A field neither the scripts nor this document carries does not
exist.

## Reading this plugin's documents

A citation that names a section — `RUN_CONTRACT.md § Every wave` — is read with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py RUN_CONTRACT.md "Every wave"`, never by
opening the file. A multi-word heading is one quoted argument.
The file is the name as the citation writes it; a path under the plugin root or an
absolute path also works. Open a file whole only where the citation names no section.

## Sign in first

Every skill that opens a run makes `get_countz_config` on the `countz` server — the
Countz connector, declared in the plugin's `.mcp.json` — its first tool call: before any
file is opened, any directory listed, any parameter collected. (The `countz` index skill
calls it too, and lists the built-in checks when that fails.) Name the tool by its short
name on that server. If the tool is not available, or the call fails, the whole reply is
this one sentence:

> Please connect the Countz connector, then come back here and I'll resume.

Nothing before it and nothing after it: no account of what was checked, no server
status, no host settings path, no summary of the data room, no next steps. The host
shows its own connect control beside that reply. Then stop.

On success, continue with the run. The result names the account and its tenant, and
carries `catalog_yaml` — the server's catalog of analyses, one entry per recipe with
`name`, `skill`, `description` and `aliases` — with its `catalog_version`. Keep it: a
skill that matches an ask against the catalog reads this copy and calls nothing again.
Every signed-in account, the testing tenant included, fetches its recipe body from the
server (`get_recipe_for_countz_analysis`) and runs everything else locally.

`get_countz_config` takes no arguments. Nothing from a run — no path, no figure,
no file name — goes to the server; the one text that may cross is the scrubbed pre-run
ask, on a catalog miss only, scrubbed by an agent under [SCRUB.md](SCRUB.md)
([OBSERVABILITY.md](OBSERVABILITY.md) § 4).

## The files, and who writes each

| file | written by | read by |
|---|---|---|
| `<run_dir>/run.json` | scripts only, run by the relay: `scripts/setup_run.py` (seed, sources, sessions, params), `scripts/run_state.py` (everything after). No agent and no dispatched step writes it | the relay, the playbook engine, dispatched steps (read-only), any human |
| `<run_dir>/engagement-preview.md` | `scripts/setup_run.py`, on every registration: the collected parameters, each source's location, and a metadata-only directory summary of every folder source (3 levels, file counts, KB) | the user, via preview, right after registration and before the first dispatch |
| `<run_dir>/file_index.json` | the plan step: every registered file with its relevance verdict (`relevant: true`, `"context"` for a file kept for later explanation, or `false`). Plan-driven runs only | dispatched steps, `scripts/preview.py` |
| `<run_dir>/sources/<id>.md` (+ `<id>.entities.json` where the source stacks several accounts, statements or entities) | the plan step, for each source its roster binds. Plan-driven runs only | the check steps |
| `<run_dir>/cache/<id>.parquet` + `<run_dir>/cache/manifest.json` | the `extract` step's script (`workpapers/extract-<check>.py`), through `scripts/cache.py`: each table the plan's steps read, parsed once into typed parquet, and the manifest — per table its source file, sha256 and bytes, header and row coordinates in the file, columns with where each sits and how it was parsed, row count, control total and any stated total; tables seen and not extracted under `not_extracted`. Plan-driven runs whose plan scheduled an extraction | the steps that name it in `params.cache_from` (`scripts/cache.py read`), `scripts/evidence.py select` for their citations. Excluded from `run_sync.tar.gz`: rebuilt by re-running the step's script, cited by nothing |
| `<run_dir>/recipes/<recipe-name>.md` | `scripts/setup_run.py --recipe` (a served recipe, byte for byte) or the `create-recipe` step (a generated one, validated by `scripts/validate_recipe.py`); written once, never edited | the plan, review and report steps, through `run.json.plan.recipe` |
| `<run_dir>/plan.md` + `<run_dir>/plan/<name>.json` | the plan step, once per draft; a revised draft rewrites both | the user (via preview), the relay, the playbook engine (the definition it executes) |
| `<run_dir>/steps/<NNNN>-<step>.json` | the step that produced it, once, at its end | the relay (`run_state.py record`), the playbook engine, the review step |
| `<run_dir>/checks/<check>.md` (and `<check>-*.csv`) | the check step that owns that check id | the review and report steps |
| `<run_dir>/workpapers/*.yaml` | the step named in the file's suffix | the review and report steps, `scripts/check_prose.py` |
| `<run_dir>/dispatch/<NNNN>-<step>.md` | `run_state.py dispatch` and `record`, one per dispatch row (a wave of one, a `--step` and a retry included), or `scripts/playbook_next.py`; on escalation, the playbook-engine agent, rendering `run_state.py`'s `BRIEF` template verbatim | that dispatch's sub-agent, as its entire launch instruction. On a plain Skill call nobody reads it at launch; it is the archive of what the fork was told |
| `<run_dir>/out/` | each step stages into `out/.staging/` and renames into place | the user, `scripts/preview.py` |
| `<run_dir>/out/run_sync.tar.gz` | the relay, via `scripts/sync_run.py`, refreshed after every wave | the user: the whole-run download (§ Bringing the run home) |
| `<run_dir>/events.jsonl` | appended by anyone, never rewritten | a human, `scripts/usage_report.py` |
| `<run_dir>/debug/` | `scripts/gather_debug.py`, every wave while debug mode is on: the per-dispatch timeline, the transcript copies and the instruction snapshot ([OBSERVABILITY.md](OBSERVABILITY.md) § 3) | a human debugging the run; `scripts/usage_report.py`, when `~/.claude/projects/` holds no transcript |

`run.json` is state and `events.jsonl` is history. State is rewritten in place. Anything
that happened and then stopped being true (a decision, a retry, a wave that died) lives in
the event log ([OBSERVABILITY.md](OBSERVABILITY.md)).

The playbook engine never writes `run.json`; it returns decisions and the relay records
them. Every write is write-to-`.tmp` then rename.

## run.json — what the fields mean

```yaml
schema: "countz-accounting/run@1"
run_id: "<the run directory's name: <skill>-<company>.<YYYYMMDD-HHMMSS>>"
goal: "checks"                      # or the playbook name a playbook or plan-driven run is executing
created_at / updated_at: "<ISO 8601 UTC>"
degraded: false                     # sticky; set when any step ends blocked or failed
inputs:
  output_root: "<abs path>"
  run_dir: "<abs path>"             # redundant on purpose: the file self-locates if copied
  skill: "qoe"                      # the launcher skill the run was minted for
  company: "Demo ZS"                # whose books, in the user's words; the directory carries its slug
  debug: false                      # debug mode (OBSERVABILITY.md § 3); sticky once on
  params: {}                        # run-level parameters collected at registration,
                                    # verbatim: period end, declared options, materiality.
                                    # Unset options take § Parameters' standing answers
  sessions:                         # every session that has touched this run
    - {session_id: "...", first_seen: "...", last_seen: "..."}
sources:                            # registered through scripts/setup_run.py
  - {id: "gl", name: "General ledger detail", path: "<abs path>",
     kind: "file"}                  # file | folder
checks:
  - {id: "tie_gl_tb", kind: "tieout",     # a kind from scripts/check_playbook.py's map
     sources: ["gl", "tb"],
     goal: "<the user's stated goal, verbatim, or null>",
     params: {},                    # tolerances or options the user declared
     seq: 3,                        # latest dispatch for this check
     status: "ok",                  # pending | ok | blocked | failed
     record: "steps/0003-tie.json"}
playbook: null                      # a playbook run sets {name, path, bound: {slot: source_id}}
plan: null                          # a plan-driven run sets {record, recipe, recipe_name,
                                    #  recipe_version, playbook, approved_at}; `recipe` is
                                    #  <run_dir>/recipes/<recipe_name>.md, the served or
                                    #  generated bytes the run pins to
dispatches: []                      # ORDERED, append-only; one entry per dispatch:
                                    # {seq, step, check_id?, skill, args, brief,
                                    #  state, record, conclusion, attempt_of?}
                                    # brief: dispatch/<NNNN>-<step>.md, the launch
                                    #   instruction; record: steps/<NNNN>-<step>.json,
                                    #   what came back
                                    # state: dispatched | ok | blocked | failed | died
next_seq: 8                         # the next unused seq; seqs are never reused
```

`checks[].id` is a slug the run mints (`tie_gl_tb`, `recon_cash`); it names the check's
files and its tab. `checks[].goal` is kept verbatim; `playbook-save` distills it into the
saved playbook.

### Parameters — the standing answers

Every `declares:` option is put to the user and stated back in the plan for their ruling.
`instructions` is always collected: the user's ask in their own words, verbatim,
whatever the entry path. It rides in `--params` and reaches the plan step as
`instructions=`, where it directs scope and emphasis and never edits the recipe or
licenses dropping a required section (`PLAYBOOK_RECIPES.md` § Running a recipe).
Where an option is still unset when the run executes:

| | unset means |
|---|---|
| who reads the deliverable | the company's own executives and operators: the CFO, the controller, the process owner. It closes on what the company does about what was found |
| a transaction reader (an M&A buyer, a seller preparing to be bought, a deal desk, a lender) | declared by the user only. A data room named `diligence`, a folder of deal files or a CIM in the room is not a declaration |
| quality of earnings | sell-side |
| an option whose line says *no default* | ask again; the run waits |
| `arr_policy` | never defaulted: settled and pinned before the plan (`ARR_POLICY.md` § How a run carries it) |

## The relay's pen — scripts/run_state.py

Every `run.json` write after registration is one of these subcommands. Each prints the
imperatives the relay executes next. A non-zero exit is put to the user, never worked
around.

- `add-checks <run_dir> --checks '<one-line JSON array>'` registers checks:
  `[{"id", "kind", "sources", "goal"?, "params"?}, ...]`, goal and params verbatim.
  Params failing the kind's contract (`PARAMS` in `scripts/check_playbook.py`) are
  refused at registration.
- `bind-playbook <run_dir> --path <definition> --bound '{"slot": "source_id", ...}'`
  records a saved playbook run: the binding, plus every fully-bound step
  registered as a check. A step fed by an unbound slot prints as `DROPPED:` and the
  engine skips it.
- `approve-plan <run_dir> --definition <run_dir>/plan/<name>.json` records the user's
  confirmation of a drafted plan: `run.json.plan` and `run.json.playbook` (a planned
  definition's slots are the run's own source ids), the steps as checks, the
  `plan_approved` event.
- `dispatch <run_dir> --checks id1,id2 [--mode fresh|fix] [--extra '<one-line JSON>']` |
  `--step plan|recipe|review|report --args '<one-line JSON>'` | `--briefs <file> ...` opens a
  wave: it allocates seqs, appends dispatch rows, writes one brief per row (every
  dispatch, a wave of one and a `--step` included) and prints one `NEXT:` line per
  member. A `NEXT:` line carries `brief=`, preceded by a `LAUNCH:` line, only when the
  wave has two or more members; a wave of one is a plain Skill call and its brief is the
  archived instruction only. The brief names the agent file the skill's frontmatter
  declares (`planner` for plan, `critic` for review, `worker` otherwise). `--briefs`
  records rows for briefs the playbook engine already wrote: the `RECORD:` line
  `playbook_next.py` prints. A `--checks` or `--step` dispatch prints its `SAY:` line
  first (§ Every wave).
- `record <run_dir>` closes a wave: it classifies every outstanding dispatch, folds
  conclusions into the checks, sets `degraded`, and mints retries, each with
  its own brief. `RETRY:` lines carry `brief=` only when two or more are minted at once. A
  minted retry wave opens with its `SAY:` line. On a debug-mode run it also prints the
  wave's `GATHER:` line.
- `debug <run_dir> [--off]` turns the run's debug mode on or off after registration.
  `setup_run.py --debug` turns it on at registration.

## The step record

`<run_dir>/steps/<NNNN>-<step>.json`, `NNNN` the zero-padded seq from the dispatch args.
Steps: `plan`, `recipe`, `arr_policy`, `extract`, `tie`, `recon`, `completeness`,
`vouch`, `cutoff`, `analyze`, `review`, `report`.

```yaml
schema: "countz-accounting/step@1"
seq: 3
step: "tie"
check_id: "tie_gl_tb"               # null for plan / review / report
args: {}                            # exactly what you were handed
started_at / completed_at: "<ISO 8601 UTC>"
outcome: "complete"                 # complete | blocked
error: null                         # a message ONLY if you could not do your work
                                    # (a crash, an input you could not open at all);
                                    # read BEFORE outcome
conclusion: "<= 2 sentences"          # what the check established, in your own words
produced: []                        # what you wrote, relative to run_dir
consumed: [{path: "<abs>", mtime: "<ISO 8601 UTC>", used_for: "..."}]
blockers: [{what: "...", effect: "..."}] # what stopped the work or narrowed it: a gate
                                    # that refused (its output, verbatim, is `what`), a
                                    # source you could not reach, a dependency that did
                                    # not land; one entry each, with its effect
findings: []                        # review only; see VALIDATION.md
cache_defects: []                   # [{id, what, fix}]: a cache id whose table the
                                    # step found wrong, and in words what the extract
                                    # script must do differently (agents/worker.md
                                    # § Your procedure)
notes: ""
```

**Write it with `scripts/step_record.py`.** `start(run_dir, seq)` appends `step_start`;
`finish(run_dir, seq, conclusion=..., blockers=..., notes=..., consumed={...})` writes
the record and appends `step_end` in one act. It reads `step`, `check_id` and `args`
from the step's own brief (`dispatch/<NNNN>-<step>.md`) and `started_at` from its
`step_start`; it builds `consumed` from the step's citations
(`workpapers/evidence-<check>.yaml`, each resolved to its file) plus the brief, the plan
and the recipe, and `produced` from the check's own files written since the start. The
step passes only what no file records: the conclusion, the blockers, the notes, a read
no citation covers (another check's record, a source profile) and, on a non-check step,
what it produced. It refuses a record the relay could not classify.

`error` is read before `outcome`. A step never marks itself successful; it reports, and
`run_state.py record` classifies. A gate that refused is `outcome: blocked` with the
gate's output in `blockers` and `error` null. Never put gate output in `error`.

## Classification and retries

`record` classifies each outstanding dispatch from its step record:

- `error` non-empty is **failed**, unless the record claims `outcome: blocked` and names a
  non-empty `blockers`, which is **blocked** whatever `error` carries.
- Otherwise `outcome` decides **ok** or **blocked**.
- A record that is absent, unparseable, or disagrees with its dispatch row is **died**.

Ok and blocked fold into the check row. Blocked also sets `degraded`; the run continues.

A first failure or death is retried once, mechanically: same args, new seq, its own
brief, `attempt_of` set. It prints as a `RETRY:` line to launch and a `THEN:` line to run
`record` again. A second failure is terminal: the check is marked `failed`, and the relay
tells the user what died and what it blocks. Review and report run over what exists, and
the deliverable states what is missing. The user decides whether to try again; the relay
never retries on its own.

## Every wave

`dispatch` opens a wave and `record` closes it. On a playbook run, `scripts/playbook_next.py`
runs first, always; the `playbook-next` skill (the agent) runs when it prints `ESCALATE:`
or fails. Execute the printed lines in their order (`SAY:`, `RECORD:`, `LAUNCH:`,
`NEXT:`, `RETRY:`, `THEN:`) and put every `FAILED:` line to the user. A `NEXT:` line
without `brief=` is a plain Skill call; it runs as the skill's fork and starts clean.

`SAY:` is the run's progress line, one per wave in either debug mode: the wave's number,
how many checks run, and what they are (the recipe's family titles on a plan-driven run;
id and kind otherwise). The plan, review and report steps and a retry each say what they
are doing. Put its text to the user as one line of plain chat, verbatim, before the
launch. Never as a file and never through SendUserFile.

After every wave, in this order:

1. Any `GATHER:` line `record` printed, the debug gather
   ([OBSERVABILITY.md](OBSERVABILITY.md) § 3). It runs before the sync so the archive
   carries the wave's trace. If it fails, say so once and keep going.
2. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/preview.py <run_dir>`. Send what it prints and
   only that. It prints nothing when nothing changed, and re-names a file whose content
   moved. With debug mode off it names only the engagement preview, `plan.md`,
   `out/workbook.xlsx` and `out/report.pptx`; with it on, every artifact
   ([OBSERVABILITY.md](OBSERVABILITY.md) § 3). What it withholds is still rendered into
   the run directory, and the sync carries it. Each `SHOW:` line is `path`, `caption`,
   `tier`. The tier decides the send:
   - `working` (the engagement preview, the source inventory, the source profiles, the
     check records, the check schedules, the deck's plan, the deck's source, the run
     summary): one SendUserFile call for the whole wave, every working path in its
     `files`, `display: attach`, the printed `BUNDLE:` line as its caption. One card per
     wave, never one per file.
   - `deliverable` (`plan.md`, the review findings, `out/workbook.xlsx`,
     `out/report.pptx`): one SendUserFile call per file, `display: render`, the printed
     caption. Of the final documents, the workbook and the report deck are deliverable;
     the summary and the deck's source (`out/report.yaml`) travel in the bundle.

   Send the bundle first, then the deliverables in printed order. Where SendUserFile does
   not exist, one line per deliverable with its path and caption, and one line for the
   bundle listing its paths.
3. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync_run.py <run_dir>`, silently. Hand
   `out/run_sync.tar.gz` to the user after a report wave lands, and whenever they ask for
   the run (§ Bringing the run home). If the refresh fails, say so once and keep going.

## Review and report

Before the review: a step record carrying `cache_defects` names a cache table the step
found wrong and what the extract script must do differently. Re-dispatch the extract
step that owns the id with `--mode fix` and `fix_input` holding those entries — it edits
its script, re-runs it, and records the control total before and after — then every step whose `params.reads` names the id,
with `--mode fix` and `fix_input` naming the id, before the review runs. The step that
found the defect computed from the source and needs no re-run.

Dispatch `check-review` (`dispatch --step review`) over the checks not yet reviewed at
their current seq. An `extract` step is not a check under review: it computes no
figure, and its record is the cache manifest every consumer's citations re-state. Put each actionable finding to the user from the review record
(severity, target, observation); with debug mode off the preview does not show them. The
user rules on each:

- **fix**: re-dispatch the named checks with `--mode fix`. Each fix snapshots its
  check first and verifies its own change by diff (`${CLAUDE_PLUGIN_ROOT}/scripts/rework.py`); that closes the finding and ends the round. No re-review follows a fix.
- **proceed**: the findings are carried into the deliverable as stated limitations.

A further round, when the user directs one, is a fresh `check-review` with `carry_from`
pointing at the prior record. A defect it re-finds standing after its fix round is put to
the user as `fix_attempted`, never fixed again. A blocking finding that stands is never
proceeded past silently: the affected figure is withheld and the deliverable says so.

Then `check-report` (`dispatch --step report`). Re-dispatch it whenever later checks or
fixes land after a seal; the report step reassembles from all current records.

The relay relays. It does not open client files, compute figures, or summarize a step's
output. The preview puts the deliverables in front of the user; the review's findings
are put to them from its record.

## Bringing the run home

`scripts/sync_run.py` moves the run directory whole, never a subset: the run's own code
and scripts, `dispatch/`, `events.jsonl`, `steps/*.json`, `out/usage.json`, and a
gathered `debug/`. Excluded: `__pycache__/`, `*.pyc`, `*.tmp`, `.DS_Store`, and the
archive itself. The sync lands the run on the user's own machine and nowhere else; no run
artifact goes to a server (`OBSERVABILITY.md` § 4).

Every mode lands the run under one folder `<short_name>.<datetime>`. The short name
defaults to the run directory's own `<skill>-<company>`; pass `--name` with the user's own
words when they give one. A `sync.json` (`run-sync@1`) sits at its top: the run id, every
session id from `run.json.inputs.sessions`, the plugin name and version the run executed
under, the source path, the sync time. `scripts/usage_report.py` prices the run from the
session ids; they also locate the session that produced the run.

When the user asks to download or sync the run to a result directory:

- **the path is writable from this machine**: `python3
  ${CLAUDE_PLUGIN_ROOT}/scripts/sync_run.py <run_dir> --dest <result_root>` copies the
  run to `<result_root>/<short_name>.<datetime>`.
- **it is not** (the run is in a cloud container; the result root is on the user's
  machine): refresh the archive, send `out/run_sync.tar.gz` (`display: attach` where
  SendUserFile exists; the path otherwise), and relay the printed `EXTRACT:` line.
  Extraction lands the run at `<result_root>/<short_name>.<datetime>`.
- **only the archive is at hand** (a pulled `run_sync.tar.gz`; the container that ran it
  is gone): `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync_run.py <archive.tar.gz> --dest
  <result_root>` lands it whole at the same layout. `--name` is refused here, and so is a
  target that already exists.

Never copy picked files (the report, the summary, the workbook) into the result root
instead of landing the run whole.
