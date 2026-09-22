# PLAYBOOK_RECIPES — the rules every recipe runs under, and how the relay drives one

A playbook recipe declares which checks substantiate a fixed objective, over which source
classes, at what grain; `check-plan` compiles it into the run's playbook. The rules below
bind every family of every recipe, and no recipe restates them. What a recipe document
must contain is `RECIPE_FORMAT.md`, read when one is written.

## What every recipe inherits

These hold on every run, and no recipe restates them.

### How a family becomes steps

A family's heading states the grain its procedure runs at — per bank account, per fiscal
year, per stream — never how many checks perform it. The plan groups the family's
entities into steps: one step over all of them, and more than one only on a measured fact
it cites (check-plan § 3). Step ids name what each step covers (`c2_accounts`,
`c4_fx_accounts`, `c9_walk`), and `params.entities` lists them.

A step covering several entities keeps them apart end to end: one declared assertion per
entity, with its own figures, citations, minted items and status, and no figure summed
across entities except as a stated total of the group. A dependent family's step reads
the step that covered its entity — `params.items_from` and its `_from` siblings name it,
one id or several — and those reads are the whole of its `after`: the plan derives the
order from them, and a recipe never states one.

The plan also schedules the data room's parsing. Every file a step reads is named in
its `params.reads`; the union of those reads is parsed once by an `extract` step the
plan adds ahead of them (`PLAYBOOKS.md` § The file), and every reader names it in
`params.cache_from`. What no step reads is never parsed.

### The source-class ladder

The class of a record sets the standing a figure drawn from
it can carry (check-plan § 3):

| class | what it is | `file_role` | standing |
|---|---|---|---|
| system-of-record | what the accounting, billing, fulfillment or treasury system exported: ledgers, trial balances, registers, subledgers, logs | `system_export` | measured |
| management-prepared | what the company's people assembled: statements as presented, schedules, reconciliations, memos, analyses, packages | `management_prepared`, `policy_document` | `as_stated`, or a candidate's support with attribution |
| underlying documents | what a counterparty, an institution or a signature produced: statements, contracts, invoices, delivery and acceptance records, correspondence | `bank_statement`, `correspondence` | `supported` |

The recipe names the class its objective rests on. A record from a lower class is tested
against it before its figures carry that standing: a reconciliation or a computation
re-performed, a balance agreed to the record, an item vouched to its support. A record
from a higher class carries its own. A management-prepared record is an input to test,
never evidence that its own conclusion holds.

### The verdict ladder

`supported`: record evidence at the standing the ruling claims.
`candidate`: the evidence points one way and the data room lacks the document that
settles it; carries the condition that would move it. `rejected`: examined and refused,
with the test it failed. `modified`: a proposed figure and the run's, side by side. A
recipe uses the subset it needs and says which.

### The subtraction runs before the verdict is chosen

Subtract the two figures at the
coarser grain (DOCTRINE.md § Working with numbers): a difference that does not survive it
is rounding, and the verdict is `supported` with the rounding stated. `modified` and
`rejected` need a difference that survives, or another attribute that moved, named with
its amount. The schedule carries the difference as its own column beside the two figures.

### Exceptions, and every other minted class

One `X.` per exception, minted
`X.<family>.<item slug>`. No minted item — exception, adjustment, leak — is netted or
aggregated past counting: its schedule lists every one and states the count and gross
amount for each group it presents.

### Reperformance

Every schedule closes with a **To reperform** block — ordered reads,
selection rule, arithmetic (EVIDENCE.md § 4, WORKBOOK.md § 6).

### The headline walk

Where `headline` is declared. One table, income-statement style:
one column per period in the set, the id column the only frozen band, the title the only
row above the header. Rows: the starting figure, citing its tie; one row per item
considered, grouped under its rung or cause, with id, name, group, signed amount per
period, verdict, then the record at the producing check's values; per group, the
supported subtotal as a conditional-sum formula over the verdict column with its result
cached (EVIDENCE.md § 4); the closing figure; information lines, never added to the
walk. No item sits only inside a subtotal. The headline check mints nothing. A supported
item whose evidence stands below its ruling is a blocking review defect.

## Running a recipe — the relay procedure

You are the relay for a plan-driven run. The recipe's frontmatter fixes the objective.
The plan step drafts the checks from the data, against the recipe; the user confirms
them before anything runs. You do no analysis and you open no client file. The recipe is
served by the Countz connector (§ 2) and pinned into the run directory; read its
frontmatter from the pinned copy. Run inline; the run records this session's id.

Read [`RUN_CONTRACT.md`](RUN_CONTRACT.md) before your first dispatch: the workspace,
`run.json` (every write goes through `scripts/setup_run.py` or `scripts/run_state.py`),
classification, and what every wave owes the user.

### 1. Collect, in one message

- **The data sources**: a short id for each and what it is. Name the recipe's source
  classes and the records each lists. Take what exists; the plan states what each
  missing record costs. Do not press.
- **The period end** covered, and **the period under review** in the user's words where
  they give one: a fiscal year, a quarter, the months of a close.
- **Each option the recipe `declares`**: put its line to the user and record the choice.
  Where they do not choose, take the answer its line carries (`RUN_CONTRACT.md`
  § Parameters).
- **The company** whose books the run is over, in the user's words. It names the run
  folder.
- **Where the output goes**: a folder you may write into. Do not guess paths.
- **The ask**, in the user's own words, as `instructions` — what they want this run to
  establish or lead with, beyond the recipe's objective. Take it from the message that
  started the run; ask for it only where that message said nothing. It never edits the
  recipe; it reaches the plan step as an argument (§ 3).

### 2. Fetch the recipe and register

Call `get_recipe_for_countz_analysis(recipe="<your recipe's name>")` on the `countz`
server — a named shim knows its name; `countz-analysis` matches the catalog first (its
SKILL.md). The result carries `recipe_markdown`, `recipe_name` and `recipe_version`.
Write `recipe_markdown` to a file, exactly as returned, then register with `--recipe`
pointing at that file and `--recipe-version` the served version: the script copies the
bytes to `<run_dir>/recipes/<recipe_name>.md` and refuses a file whose sha does not
match the version, so the run pins the bytes the server served. A named shim sends no
`ask`. `match: not_found` for a named recipe means the server no longer carries it: put
that to the user and stop.

The registration:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py \
    --output-root <abs> --skill <your shim's name> --company "<the user's words>" \
    --goal <the recipe's name> --session ${CLAUDE_SESSION_ID} \
    --sources '[{"id": "gl", "path": "<abs>", "name": "<the user's words>"}, ...]' \
    --params '{"period_end": "<as collected>", "period": "<as collected, where given>",
               "instructions": "<the ask, verbatim>", "<declared key>": "<the choice>", ...}' \
    --recipe <the file you wrote> --recipe-version <recipe_version>
```

The script mints `<output_root>/<skill>-<company slug>.<YYYYMMDD-HHMMSS>` and prints it
as `RUN_DIR:`; that path is `<run_dir>` everywhere below. Never compose the name
yourself. `--params` is everything § 1 collected, verbatim, as one JSON object — the
ask included, so `run.json` records why the run was scoped as it was. The script reads
no client file. A `countz-analysis` run on a catalog miss registers without `--recipe`
and pins the generated recipe afterwards (its SKILL.md).

Sources arriving after the plan is drafted: run the same script with `<run_dir>` in place
of `--output-root`, `--skill` and `--company`, then re-dispatch `check-plan` with
`revise=` naming them.

The script also writes `<run_dir>/engagement-preview.md`: the parameters, each source's
location and the data room's directory shape, from directory metadata only. Before
dispatching the plan, run `scripts/preview.py <run_dir>` and send what it prints
(RUN_CONTRACT.md § Every wave).

**Debug mode.** When the user asks for it, add `--debug` and say once what it turns on:
every wave gathers the session transcripts into `<run_dir>/debug/`, which then carries
each dispatch's prompts, tool calls and model output and stays on this machine
([`OBSERVABILITY.md`](OBSERVABILITY.md) § 3 and § 4); the preview shows every working
paper and the review findings instead of only the engagement preview, the plan, the
workbook and the report deck. `run_state.py debug <run_dir>` turns it on mid-run.

### 3. Plan

Dispatch `check-plan` as a wave of one: `run_state.py dispatch <run_dir> --step plan
--args '<one-line JSON>'`, then a plain Skill call. Arguments: `recipe=` the pinned
recipe's absolute path (`<run_dir>/recipes/<name>.md`, never a plugin path), `name=` and
`objective=` from its frontmatter (objective verbatim), `instructions=` the ask
verbatim, `period_end`, `period` where collected, and `declared=` the collected values
where the recipe declares options. The recipe is read as written: `instructions` shapes
the plan, not the recipe. The planner indexes every file with a relevance verdict against
the objective, reads what the recipe needs, records the entities rosters and drafts the
definition.

`record`, preview (`plan.md` reaches the user), then put the plan to them: what runs per
entity and at what grain, what was set aside and why, what is degraded or dropped and
what data would restore it, and every proposed parameter awaiting confirmation, windows
first. Their ruling decides:

- confirm: `run_state.py approve-plan <run_dir> --definition <plan path>`. Records
  `run.json.plan` and `run.json.playbook`, registers the steps as checks, appends
  `plan_approved`.
- adjust: re-dispatch `check-plan` with `revise=` their instruction on a new seq, an
  overruled set-aside file included.
- stop.

Nothing below runs before the user has seen the plan.

### 4. Execute

The `playbook` skill's run loop. Run
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/playbook_next.py <run_dir> <definition path>` and
execute the lines it prints in order: `RECORD:`, `LAUNCH:`, `NEXT:`, then the `THEN:`
lines (`record`, any `RETRY:`, the script again). On `ESCALATE:` (exit code 3) or any
other failure, invoke the `playbook-next` skill with the same arguments, execute its
imperatives, then return to the script. Repeat until `DONE:`. Relay any skipped or failed
steps it names.

### 5. Review and report

Per `RUN_CONTRACT.md` § Review and report: `check-review` over the unreviewed checks, the
user's ruling on its findings, then `check-report` with the plan's report title.

### 6. Close

The deliverables are `out/workbook.xlsx` and `out/report.pptx`; the report wave's preview
put them on screen as rendered cards. `out/RUN_SUMMARY.md` is in that wave's working
bundle on a debug-mode run and in the run directory otherwise. Point at all three. Hand
over the run archive `out/run_sync.tar.gz` per `RUN_CONTRACT.md` § Bringing the run home;
extracted under the user's result root it lands at `<short_name>.<datetime>` with
`sync.json` carrying the run's session ids. Relay the exception schedule and the open
items, each with its amount, what closes it and who owns it, and the coverage the run
achieved. Invite instructions: a directed fix re-runs the owning check and reseals the
report.
