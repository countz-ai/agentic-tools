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
Countz connector, declared in the plugin's `.mcp.json` — its first tool call after the
skill's opening command, where it has one: before any client file is opened, any
directory listed, any parameter collected. (The `countz` index skill calls it too, and
lists the built-in checks when that fails.) Name the tool by its short name on that
server. If the tool is not available, or the call fails, the whole reply is
the message below, written as it stands, as markdown (the fence is not part of the
reply):

```markdown
**Add Countz connector to run this analysis**

Countz Connector supplies the procedure recipe for this analysis, in its most recently tuned version. No financial data ever goes to Countz.

**To connect**
1. Open **Settings → Plugins**.
2. Open the details of the **Countz** plugin and go to the **Connectors** tab.
3. Connect Countz and sign in.

Then come back here and say **resume**. I'll start this analysis from your original request.

Details: [countz.ai/docs/plugin](https://www.countz.ai/docs/plugin.html)
```

Add nothing before it or after it: no account of what was checked, no server status, no
error text, no summary of the data room. Then stop. When the user comes back, call
`get_countz_config` again and, on success, run the skill on the ask they made before
the failure.

On success, continue with the run. The result names the account and its tenant, and
carries:

- `catalog_yaml` — the server's catalog of analyses, one entry per recipe with `name`,
  `skill`, `description` and `aliases` — with its `catalog_version`. Keep it: a skill
  that matches an ask against the catalog reads this copy and calls nothing again.
- `blocked_tools` — the MCP tools this session must not call, set for the tenant; the
  user cannot change it, and it is empty unless the tenant sets it. An entry is
  `<server>/<tool>`, `<server>/*`, or `*`. The `countz` server refuses its own listed
  tools on every call, with an error that carries `tool_blocked:`.

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
| `<run_dir>/cache/<id>.parquet` + `<run_dir>/cache/not_extracted.json` | the `extract` step's script (`workpapers/extract-<check>.py`), through `scripts/cache.py`: each table the plan's steps read, parsed once into typed parquet holding its metadata (schema `cache@4`) — what one row is, its source file, sha256 and bytes, header and row coordinates in the file, each column's description, unit, location and parse, row count, control total and any stated total, and the rows' sha256 that `cache.py --verify` re-checks; tables seen and not extracted in `not_extracted.json`. Plan-driven runs whose plan scheduled an extraction | the steps that name it in `params.cache_from`, which read it in SQL as `room.<id>` (`scripts/sql.py`). Excluded from `run_sync.tar.gz`: rebuilt by re-running the step's script, cited by nothing |
| `<run_dir>/tables/<check>/<name>.parquet` | the check step, through `run_sql("CREATE ... TABLE <check>.<name> AS SELECT ...")`: one table it derived, holding the statement and what it read | later statements, as `<check>.<name>`; `sql.py verify`, which re-runs the statement |
| `<run_dir>/constants/<check>.json` | the check step, through `Ledger.constants`: the values a document states (with file, locator and quote) and the values the step chose (with its basis) | later statements, as rows of `room.constants`; `sql.py verify`, which re-checks each quote |
| `<run_dir>/catalog.sql` | `scripts/sql.py`, after every table, ledger or constants write: the views over every table, `room.constants`, `countz.*`, the macros | `scripts/countz-sql -init` |
| `<run_dir>/recipes/<recipe-name>.md` | `scripts/setup_run.py --recipe` (a served recipe, byte for byte) or the `create-recipe` step (a generated one, validated by `scripts/validate_recipe.py`); written once, never edited | the plan, review and report steps, through `run.json.plan.recipe` |
| `<run_dir>/plan.md` + `<run_dir>/plan/<name>.json` | the plan step, once per draft; a revised draft rewrites both | the user (via preview), the relay, the playbook engine (the definition it executes) |
| `<run_dir>/plan/spend-estimate.json` | `scripts/spend_model.py estimate`, run by the plan step on each draft: predicted cost and minutes per step and family, the run total and elapsed time, each with its range, from `reference/spend_model.json` | the plan step, which copies its table into `plan.md` |
| `<run_dir>/steps/<NNNN>-<step>.json` | the step that produced it, once, at its end | the relay (`run_state.py record`), the playbook engine, the review step |
| `<run_dir>/workpapers/<check>.tpl.md` | the check step that owns that check id: its page, one template (`WORKBOOK.md` § 7) | `scripts/render.py` |
| `<run_dir>/checks/<check>.md` (and `<check>-*.parquet`, its item tables) | the check step that owns that check id; the md rendered from its template | the review and report steps; SQL as `<check>.<table>` |
| `<run_dir>/checks/<check>-summary.md` | a plan-driven check step, rendered from its template's `## Summary`: whether its procedure worked and where it stands, in an accountant's words (`agents/worker.md` § Files) | `scripts/family_artifacts.py` |
| `<run_dir>/out/families/<NN>-<title>.md` + `.xlsx` | `scripts/family_artifacts.py`, after every wave, for each family whose checks are all terminal: the family's summary and its workbook, its check tabs in one file | the user, via preview |
| `<run_dir>/workpapers/*.yaml` | the step named in the file's suffix | the review and report steps, `scripts/check_prose.py` |
| `<run_dir>/dispatch/<NNNN>-<step>.md` | `run_state.py dispatch` and `record`, one per dispatch row (a wave of one, a `--step` and a retry included), or `scripts/playbook_next.py`; on escalation, the playbook-engine agent drafts it from `run_state.py`'s `BRIEF` template and `dispatch --briefs` re-renders it from its argument block. A plan-driven step's brief carries its family section and the schedules the deck takes from its tab | that dispatch's sub-agent, as its entire launch instruction. On a plain Skill call nobody reads it at launch; it is the archive of what the fork was told |
| `<run_dir>/dispatch/recipe-rules.md` | `run_state.py`, which rewrites it with every plan-driven brief. It holds `PLAYBOOK_RECIPES.md` § What every recipe inherits, then the pinned recipe from its start to `## The families` | every plan-driven step, which reads it once instead of the recipe (`agents/worker.md` § Your procedure) |
| `<run_dir>/out/` | each step stages into `out/.staging/` and renames into place | the user, `scripts/preview.py` |
| `<run_dir>/out/run_sync.tar.gz` | the relay, via `scripts/sync_run.py`, refreshed after every wave | the user: the whole-run download (§ Bringing the run home) |
| `<run_dir>/events.jsonl` | appended by anyone, never rewritten | a human, `scripts/usage_report.py` |
| `<run_dir>/debug/` | `scripts/gather_debug.py`, run by hand on a run under diagnosis: the per-dispatch timeline, the transcript copies and the instruction snapshot ([OBSERVABILITY.md](OBSERVABILITY.md) § 3) | a human debugging the run; `scripts/usage_report.py`, when `~/.claude/projects/` holds no transcript |

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
  params: {}                        # run-level parameters collected at registration,
                                    # verbatim: period end, declared options, materiality.
                                    # Unset options take § Parameters' standing answers
  scope: {picked, families, added}  # optional: the recipe families the user picked, and
                                    # with the ones they read from, in recipe order
                                    # (setup_run.py --scope;
                                    # PLAYBOOK_RECIPES.md § Ask what to run).
                                    # Absent: every family runs
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
                                    #  generated bytes the run pins to. A scoped run adds
                                    #  scope: {picked, families}, the families the
                                    #  approved steps run: what review and report hold
                                    #  the deliverable to
dispatches: []                      # ORDERED, append-only; one entry per dispatch:
                                    # {seq, step, check_id?, skill, args, brief,
                                    #  state, record, conclusion, attempt_of?}
                                    # brief: dispatch/<NNNN>-<step>.md, the launch
                                    #   instruction; record: steps/<NNNN>-<step>.json,
                                    #   what came back
                                    # state: dispatched | ok | blocked | failed | died
next_seq: 8                         # the next unused seq; seqs are never reused
```

`checks[].id` is an id the run mints (`tie_gl_tb`, `recon_cash`), `[a-z0-9][a-z0-9_]*`;
it names the check's files and its tab. It takes no `-`, which separates the check id
from the table name in `checks/<check>-<table>.parquet`. It is at most 31 characters, the
longest tab name Excel holds: the check's tab opens with the id, and the workbook gate
traces each tab to its check by that opening. `checks[].goal` is kept verbatim;
`playbook-save` distills it into the saved playbook.

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
  `plan_approved` event. On a scoped run it refuses a step outside `inputs.scope` that
  no step inside it reads, and records `plan.scope`.
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
  minted retry wave opens with its `SAY:` line.

**The brief's argument block.** After the line `Your arguments:`, one line per argument,
`    key=value` (four spaces), the key `[A-Za-z0-9_]+`. A value holding a line break,
starting with `"`, carrying leading or trailing whitespace, or spelled `(none)` is
written as one JSON string. A bare `(none)` is an empty value. A list of non-empty plain
strings with no comma is comma-joined; any other value is compact JSON. `run_state.py`
writes every brief this way, and `parse_brief_args` reads the block back for it and for
`step_record.py`. `dispatch --briefs` refuses a block holding any other line, a key
twice, or a value starting with `"` that is not one JSON string.

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
step supplies only what no file records: the conclusion, the blockers, the notes, a read
no citation covers (another check's record, a source profile) and, on a non-check step,
what it produced. It refuses a record the relay could not classify, an `error` that is
neither null nor a non-empty message, an extra field naming one the record derives
(`schema`, `step`, `check_id`, `args`, `started_at`, ...), and a `produced` path that
does not exist under the run directory.

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
brief, `attempt_of` set. A second is retried once more as a repair: the same args plus
`prior_errors`, what stopped each earlier attempt, verbatim, so the step reads why it
failed and takes another route (`agents/worker.md` § Your procedure). Each prints as a
`RETRY:` line to launch and a `THEN:` line to run `record` again. A third failure is
terminal: the check is marked `failed`, and the relay tells the user in one line what
failed and what it blocks, and goes on. Review and report run over what exists, and the
deliverable states what is missing.

## Running to completion

The user approves the plan. From then the run goes on to the deliverable without
waiting for a ruling: the relay launches every wave, every retry and every fix round the
scripts and this document call for, and tells the user what happened in the `SAY:` lines
and the previews. A defect the run can repair, it repairs: a step that failed is
retried (§ Classification and retries), a cache table found wrong is re-extracted, and
a review finding is fixed (§ Review and report).

The run stops to ask only about the data room: a question about the company's records
that the user can answer and the files cannot, where the answer decides a figure a later
step stands on, and the run would otherwise guess (examples: which of two disagreeing
schedules is the one management closed on; whether an account missing from the trial
balance was closed or left out of the export). Put every such question in one message,
each in a sentence with what its answer changes, and wait. A question nothing turns on
is not asked: it is carried to the open items.

## Every wave

`dispatch` opens a wave and `record` closes it. On a playbook run, `scripts/playbook_next.py`
runs first, always; the `playbook-next` skill (the agent) runs when it prints `ESCALATE:`
or fails. Execute the printed lines in their order (`SAY:`, `RECORD:`, `LAUNCH:`,
`NEXT:`, `RETRY:`, `THEN:`) and put every `FAILED:` line to the user. A `NEXT:` line
without `brief=` is a plain Skill call; it runs as the skill's fork and starts clean.
A `LAUNCH:` wave runs as `countz-accounting:worker` sub-agents, the agent type every
check skill forks into. Their system prompt is the worker charter followed by
`CONDUCT.md`, `DOCTRINE.md` and `EVIDENCE.md`, which `scripts/build_agents.py` appends to
`agents/worker.md`. No step starts by reading those documents, and the whole wave shares
them as one cached prefix.

`SAY:` is the run's progress line, one per wave: the wave's number,
how many checks run, and what they are (the recipe's family titles on a plan-driven run;
id and kind otherwise). The plan, review and report steps and a retry each say what they
are doing. The line opens with the run's position.
Example: `Step 3 of 6:`, or `Steps 2–4 of 6:` for a wave of three. On a plan-driven run
the steps are the recipe families the run performs, in recipe order: the unit of the
steps table the user picked from (`PLAYBOOK_RECIPES.md` § Ask what to run), counting only
the families this run carries, so a step left out, at either end or in the middle, is
not counted. A wave's position is that of the families its checks perform, and a family
run as several checks is one step; the line names each by its title. The extract step,
the review and the report perform no family and carry no position. On any other run the
steps are its checks in first-dispatch order, then the review and the report; the total
drops a check that will not run: a skipped playbook step, or a check with no dispatch
when the review is dispatched. A retry or a fix carries the number its check first took.
The plan, recipe and ARR-policy steps carry no position: they run before the plan
registers any check. Put its text to the
user as one line of plain chat, verbatim, before the launch. Never as a file and never
through SendUserFile.

After every wave, in this order:

1. `uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/family_artifacts.py <run_dir>`,
   silently: it writes each finished family's summary and workbook under
   `out/families/`, and leaves the rest as it was. If it fails, say so once and keep
   going.
2. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/preview.py <run_dir>`. Send what it prints and
   only that. It prints nothing when nothing changed, and re-names a file whose content
   moved. It names every artifact as it lands. Each `SHOW:` line is `path`, `caption`,
   `tier`. The tier decides the send:
   - `working` (the engagement preview, the source inventory, the source profiles, the
     check records and check schedules of a run without families, the deck's plan, the
     deck's source, the run summary): one SendUserFile call for the whole wave, every working path in its
     `files`, `display: attach`, the printed `BUNDLE:` line as its caption. One card per
     wave, never one per file.
   - `deliverable` (`plan.md`, each family's summary and then its workbook, the review findings,
     `out/workbook.xlsx`, `out/report.pptx`): one SendUserFile call per file, `display: render`, the printed
     caption. Of the final documents, the workbook and the report deck are deliverable;
     the summary and the deck's source (`out/report.yaml`) travel in the bundle.

   Send the bundle first, then the deliverables in printed order, one call at a time:
   each call waits for the one before it, never several in one turn. Where SendUserFile does
   not exist, one line per deliverable with its path and caption, and one line for the
   bundle listing its paths.
3. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync_run.py <run_dir>`, silently. Hand
   `out/run_sync.tar.gz` to the user after a report wave lands, and whenever they ask for
   the run (§ Bringing the run home). If the refresh fails, say so once and keep going.

## Holder lanes

A playbook run's steps run in a few holder lanes when you have both the Agent tool and
SendMessage. A lane is one `countz-accounting:worker` sub-agent that you launch once and
continue with SendMessage, so each step reads in its context what the lane's earlier steps
read and wrote; the lanes run in parallel. Without SendMessage, the run moves in waves as
§ Every wave states and you skip this section.

1. **Assign the lanes once**, after the plan is approved (a saved playbook: after
   `bind-playbook`) and before the first `playbook_next.py` call:
   `uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lanes.py assign <run_dir> <definition path>`.
   It maps the approved plan's steps (only those, so a partial run's scope is what runs)
   onto at most three lanes and writes `<run_dir>/lanes.json`. Say nothing about it.
2. **Run the loop as before**: `playbook_next.py`, then the lines it prints in order. On a
   lanes run it prints, instead of `LAUNCH:` and `NEXT:`, a `RECORD:` line, one
   `LANE: lane=<L> holder=<new|agentId> seq=<n> check=<id> brief=<path>` line per step it
   starts, and an `AWAIT:` line; or `WAIT:` when nothing can start until a lane reports
   back. Execute `RECORD:` first, then every `LANE:` line of the call in one message:
   - `holder=new`: launch one sub-agent of subagent_type `countz-accounting:worker`
     (general-purpose where that type is not available), in the background, prompted
     exactly: `Read <brief> and do what it says. It is your entire instruction for this
     step.` Then record its agentId:
     `uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lanes.py holder <run_dir> --lane <L> --agent <agentId>`.
   - `holder=<agentId>`: SendMessage to that agentId, the message exactly: `Next step:
     read <brief> and do what it says. It is your entire instruction for this step.`
     If SendMessage refuses or fails, run
     `uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lanes.py fallback <run_dir> --lane <L>` and
     execute the `LANE:` line it prints (a new holder for the same brief).
3. **When a lane's agent reports back** — the Agent call's result, a task notification,
   or the SendMessage call's own result (where SendMessage waits for the worker, as in a
   cloud session, the reply is in the call's result) — run
   `uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lanes.py done <run_dir> --agent <its agentId>`.
   It closes that step alone (`run_state.py record --seqs`), so the steps still running in
   other lanes stay open; put its `OK:`, `BLOCKED:` and `FAILED:` lines to the user as
   § Classification and retries states, execute a `LANE:` line it prints (the failed
   step's retry, in the same lane on a new holder), then the after-wave steps of § Every
   wave, then its `THEN:` line (`playbook_next.py` again). Handle one report at a time.
4. **On `DONE:`** the review and report tail runs as § Review and report states: the
   review and the report steps as fresh sub-agents, and each fix round in the lanes
   through `lanes.py fix`, every re-run on the lane that ran its check.

`lanes.py` decides which lane runs what and when a holder is replaced; you never choose a
lane, reuse an agentId the script did not print, or fork a context. A holder whose
context passes 700,000 tokens is replaced by a new one at its lane's next step, and a
brief for a holder that ran some of its inputs hands over only the rest
(`scripts/handoff.py`).

## Review and report

Before the review: a step record carrying `cache_defects` names a cache table the step
found wrong and what the extract script must do differently. Re-dispatch the extract
step that owns the id with `--mode fix` and `fix_input` holding those entries — it edits
its script, re-runs it, and records the control total before and after — then every step whose `params.reads` names the id,
with `--mode fix` and `fix_input` naming the id, before the review runs. The step that
found the defect computed from the source and needs no re-run.

Dispatch `check-review` (`dispatch --step review`) over the checks not yet reviewed at
their current seq. An `extract` step is not a check under review: it computes no
figure, and its record is the cache manifest every consumer's citations re-state. Act on
every finding in the review record by its `fix_kind`, without waiting for a ruling
(§ Running to completion), and tell the user in one line what the fix round re-runs:

- **`rerun_check`**: re-dispatch the named checks with `--mode fix`. Each fix snapshots
  its check first and verifies its own change by diff
  (`${CLAUDE_PLUGIN_ROOT}/scripts/rework.py`); that closes the finding and ends the
  round. No re-review follows a fix.
- **`withhold`**: the figure is withheld, and the deliverable says so.
- **`review_call`**: carried into the deliverable as a stated limitation.
- **`data_request`** and **`management_question`**: the data room cannot settle them. Where
  the answer decides a figure, put them to the user as § Running to completion says; an
  answer re-dispatches the named check with `--mode fix`, the answer verbatim in
  `fix_input`. Otherwise, and on no answer, they are carried to the open items.

On a holder-lanes run (§ Holder lanes), every re-dispatch this section calls for — a fix
of a review finding, a re-extract for a cache defect and the re-runs after it, a check
re-dispatched with an answer — goes through
`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lanes.py fix <run_dir> --checks <ids> --mode fix
[--extra '<one-line JSON>']` instead of `run_state.py dispatch --checks`, with the same
checks, mode and extra. It sends each re-run to the lane that ran its check, warm on
that lane's holder, one at a time per lane. Execute its `LANE:` lines and each report
back as § Holder lanes states; when `lanes.py done` prints `ROUND DONE:`, go on here.

A further round, when the user directs one, is a fresh `check-review` with `carry_from`
pointing at the prior record. A defect it re-finds standing after its fix round is
`fix_attempted`, never fixed again, and carried as a stated limitation. A blocking
finding that stands is never proceeded past silently: the affected figure is withheld
and the deliverable says so.

Then `check-report` (`dispatch --step report`). Re-dispatch it whenever later checks or
fixes land after a seal; the report step reassembles from all current records.

The relay relays. It does not open client files, compute figures, or summarize a step's
output. The preview puts the deliverables and the review's findings in front of the
user.

## Bringing the run home

`scripts/sync_run.py` moves the run directory whole, never a subset: the run's own code
and scripts, `dispatch/`, `events.jsonl`, `steps/*.json`, `out/usage.json`, and a
gathered `debug/`. Excluded: `__pycache__/`, `*.pyc`, `*.tmp`, `.DS_Store`, and the
archive itself. The sync lands the run on the user's own machine and nowhere else.

Every mode lands the run under one folder `<short_name>.<datetime>`. The short name
defaults to the run directory's own `<skill>-<company>`; set `--name` to the user's own
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
