# PLAYBOOK_RECIPES — the rules every recipe runs under, and how the relay drives one

A playbook recipe declares which checks substantiate a fixed objective, over which source
classes, at what grain, and how the deliverable tells the result; `check-plan` compiles
it into the run's playbook. The rules under § What every recipe inherits bind every
family of every recipe. `RECIPE_FORMAT.md` states what a recipe document must contain;
read it before you write one.

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
plan adds ahead of them, through its worker's own script and `scripts/cache.py`
(`PLAYBOOKS.md` § The file), and every reader names it in
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

`supported`: record evidence at the standing the ruling claims. A `supported` ruling
whose evidence carries a lower standing is a `blocking` finding (VALIDATION.md § Severity).
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
amount for each group it presents. A family that rolls up other families' items mints
nothing. It lists every item it rolls up, and each row carries the id and values of the
check that produced the item.

### Reperformance

Every schedule closes with a **To reperform** block — ordered reads,
selection rule, arithmetic (EVIDENCE.md § 4, WORKBOOK.md § 6).

## Running a recipe — the relay procedure

You are the relay for a plan-driven run. The recipe's frontmatter fixes the objective.
The plan step drafts the checks from the data, against the recipe; the user confirms
them before anything runs. You do no analysis and you open no client file. The recipe is
served by the Countz connector (§ 3) and pinned into the run directory; read its
frontmatter from the pinned copy. Run inline; the run records this session's id.

Read [`RUN_CONTRACT.md`](RUN_CONTRACT.md) before your first dispatch: the workspace,
`run.json` (every write goes through `scripts/setup_run.py` or `scripts/run_state.py`),
classification, and what every wave owes the user.

### 1. Ask what to run

This is the run's first question, and it goes to the user before anything else is done:
no file written, no folder made, no other question asked.

1. Get the recipe your skill names. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/bundled_recipe.py
   <its name>` (your skill's first command runs it) prints `RECIPE:` and `VERSION:` when
   the package carries a copy: that path is the recipe. On `NONE`, call
   `get_recipe_for_countz_analysis(recipe="<its name>")` on the `countz` server; the
   body is its `recipe_markdown`. Do not write the served body to a file: § 3 pins it after the
   user answers, from the saved result where the host saved one.
2. Read the user's request against the family headers. The request is the text that
   invoked the skill: the arguments after its name, or the message that started the
   run. It is **specific** when it names a measure, a cut, an account, a population or
   a question that only some of the families answer (example: *"show me the ARR and
   retention for various dimensions in my data"*, on the ARR recipe, bears on the
   customer revenue cube and the ARR roll-forward & retention). It is **broad** when it
   asks for the analysis as a whole. On a specific request, take the
   families whose headers answer it: the ones it bears on directly, not the ones they
   read from, which registration adds.
3. Print the choice, with `--suggest <their ids, comma-separated>` on a specific
   request and without it on a broad one. For a bundled copy, pass its path:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/recipe_scope.py ask <the RECIPE path>`. For a
   served body, pipe in only its family headers, the lines that open `### ` under
   `## The families`, copied exactly:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/recipe_scope.py ask --suggest c4,c5 <<'EOF'
   ### C0 — the population, drawn from the balance sheet (kind `analysis`, one check)
   ...
   EOF
   ```

4. Send what the script prints between `SHOW:` and `END`, verbatim, as the whole
   message: the recipe's steps as a numbered overview, and under it the prompt. On a
   broad request the prompt asks what to run, *run 5, 6* or *run all*; on a specific
   one it proposes the steps the request bears on, *Based on your request, steps 5, 6
   are relevant, shall we run them?* Use no question tool: the user reads the whole
   list, then answers in their own words.
5. Stop. Your turn ends with that message. Once the user has answered, read
   `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md` whole and the rest of this procedure
   (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py PLAYBOOK_RECIPES.md "Running a recipe"`)
   where you have not read them, and go on from § 2.

The `KEY:` lines are yours alone: each maps a row number to its family id and title.
Read the user's answer through them. A yes to a proposal runs the steps it proposed.
Otherwise read the picks — the numbers or the step names they typed — as row numbers.
*Run all*, or an answer that names no step and accepts no proposal, is the whole
recipe. A step a pick reads from is added at registration. Never put a family id, an
underscore or the code's own markup in front of the user.

### 2. Collect, in one message

Once the user has picked what to run (§ 1), ask the rest in one message:

- **The data sources**: a short id for each and what it is. Name the recipe's source
  classes and the records each lists. Take what exists; the plan states what each
  missing record costs. Do not press.
- **The period end** covered, and **the period under review** in the user's words where
  they give one: a fiscal year, a quarter, the months of a close.
- **Each option the recipe `declares`**: put it to the user in plain words (what it
  controls, its default, what changing it does) and record the choice.
  Where they do not choose, take the answer its line carries (`RUN_CONTRACT.md`
  § Parameters). `arr_policy` is the exception: it is a file, not a one-line choice. Ask
  whether the company has an approved ARR policy (`ARR_POLICY.md` § Where a policy
  lives). A policy in the library for this company (`arr_policy.py library`, its
  `MATCH:` line) is offered by name. The rest is
  settled after registration (§ 3).
- **The accounting standard** (`accounting_standard`), if the user names one.
- **The company** whose books the run is over, in the user's words. It names the run
  folder.
- **Where the output goes**: a folder you may write into. Do not guess paths.
- **The ask**, in the user's own words, as `instructions` — what they want this run to
  establish or lead with, beyond the recipe's objective. Take it from the message that
  started the run; ask for it only where that message said nothing. It never edits the
  recipe; it reaches the plan step as an argument (§ 4).

### 3. Fetch the recipe and register

§ 1 fetched the recipe; now write the served body to a file and register it with the
collected answers and the picks. The fetch itself:

First look for a bundled copy:
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/bundled_recipe.py <your recipe's name>`. When it
prints `RECIPE:` and `VERSION:`, the package was built with that recipe in it: say so to
the user in one line, register with `--recipe <the RECIPE path> --recipe-version <the
VERSION>`, and call no recipe tool. `NONE` means nothing is bundled: fetch.

Call `get_recipe_for_countz_analysis(recipe="<your recipe's name>")` on the `countz`
server — a named shim knows its name; `countz`, given an ask, matches the catalog first
(its SKILL.md). The result carries `recipe_markdown`, `recipe_name` and `recipe_version`.
Pin it one of two ways; either way the script copies the bytes to
`<run_dir>/recipes/<recipe_name>.md` and refuses bytes whose sha does not match the
version, so the run pins the bytes the server served:

- **The host saved the result to a file** (it shows the file's path in place of the full
  result): register with `--recipe-result <that path>` and write nothing yourself. The
  script reads `recipe_markdown` and `recipe_version` from the file. This is the fast way:
  copying the body out by hand takes minutes.
- **Otherwise**, write `recipe_markdown` to a file, exactly as returned, and register with
  `--recipe` pointing at that file and `--recipe-version` the served version. If
  `--recipe-result` refused the file, do the same. A named shim sends no
`ask`. `match: not_found` for a named recipe means the server no longer carries it: put
that to the user and stop.

The registration:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py \
    --output-root <abs> --skill <your shim's name> --company "<the user's words>" \
    --goal <the recipe's name> --session ${CLAUDE_SESSION_ID} \
    --sources '[{"id": "gl", "path": "<abs>", "name": "<the user's words>"}, ...]' \
    --params '{"period_end": "<as collected>", "period": "<as collected, where given>",
               "accounting_standard": "<if the user named one>",
               "instructions": "<the ask, verbatim>", "<declared key>": "<the choice>", ...}' \
    --recipe-result <the saved result> \
    --scope <the picks: row numbers, or all>
```

Without a saved result, `--recipe <the file you wrote> --recipe-version <recipe_version>`
stands in place of `--recipe-result`.

The script mints `<output_root>/<skill>-<company slug>.<YYYYMMDD-HHMMSS>` and prints it
as `RUN_DIR:`; that path is `<run_dir>` everywhere below. Never compose the name
yourself. `--params` is everything § 2 collected, verbatim, as one JSON object — the
ask included, so `run.json` records why the run was scoped as it was. The script reads
no client file. A `countz` run on a catalog miss registers without `--recipe`
and pins the generated recipe afterwards (its SKILL.md).

**The scope.** `--scope` resolves the picks with every family they read from into
`run.json.inputs.scope`, and prints `SCOPE:` and `SAY:`. Put the `SAY:` text to the user
in one line, verbatim: it names what runs and what was added because a pick depends on
it. `all` registers no scope, and the run executes every family. To change the scope
before the plan is approved, run `setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID}
--sources '[]' --scope <picks>`, then re-dispatch `check-plan` with `revise=` naming the
change.

Sources arriving after the plan is drafted: run the same script with `<run_dir>` in place
of `--output-root`, `--skill` and `--company`, then re-dispatch `check-plan` with
`revise=` naming them.

**The ARR policy.** Where the recipe declares `arr_policy`, pin an approved policy before
the plan: the one the user named, or the library's for this company, with
`setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID} --sources '[]' --arr-policy
<path>`. Where there is none, or `--arr-policy` refuses the file, invoke the
`create-arr-policy` skill with `run_dir` and `company`; it settles, saves and pins the
policy.

The script also writes `<run_dir>/engagement-preview.md`: the parameters, each source's
location and the data room's directory shape, from directory metadata only. Before
dispatching the plan, run `scripts/preview.py <run_dir>` and send what it prints
(RUN_CONTRACT.md § Every wave).

### 4. Plan

Dispatch `check-plan` as a wave of one: `run_state.py dispatch <run_dir> --step plan
--args '<one-line JSON>'`, then a plain Skill call. Arguments: `recipe=` the pinned
recipe's absolute path (`<run_dir>/recipes/<name>.md`, never a plugin path), `name=` and
`objective=` from its frontmatter (objective verbatim), `instructions=` the ask
verbatim, `period_end`, `period` where collected, and `declared=` the collected values
where the recipe declares options. On a scoped run, `dispatch` adds `families=` to the
`NEXT:` line: the plan's to-do list, which the planner plans from instead of every
family. Pass the line's arguments as printed. The recipe is read as written: `instructions` shapes
the plan, not the recipe. The planner indexes every file with a relevance verdict against
the objective, reads what the recipe needs, records the entities rosters and drafts the
definition.

`record`, preview (`plan.md` reaches the user), then put the plan to them: what runs per
entity and at what grain, what was set aside and why, what is degraded or dropped and
what data would restore it, and every proposed parameter awaiting confirmation, windows
first. Their ruling decides:

- confirm: `run_state.py approve-plan <run_dir> --definition <plan path>`. Records
  `run.json.plan` and `run.json.playbook`, registers the steps as checks, appends
  `plan_approved`. On a scoped run it refuses a step outside the scope that no step in
  it reads; re-dispatch `check-plan` with `revise=` quoting the refusal.
- adjust: re-dispatch `check-plan` with `revise=` their instruction on a new seq, an
  overruled set-aside file included.
- stop.

Nothing below runs before the user has seen the plan. Once they confirm it, the run goes
on to the deliverable without asking again, except about the data room
([`RUN_CONTRACT.md`](RUN_CONTRACT.md) § Running to completion).

### 5. Execute

The `playbook` skill's run loop. Run
`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/playbook_next.py <run_dir> <definition path>` and
execute the lines it prints in order: `RECORD:`, `LAUNCH:`, `NEXT:`, then the `THEN:`
lines (`record`, any `RETRY:`, the script again). On `ESCALATE:` (exit code 3) or any
other failure, invoke the `playbook-next` skill with the same arguments, execute its
imperatives, then return to the script. Repeat until `DONE:`. Relay any skipped or failed
steps it names. With SendMessage available the steps run in holder lanes instead of waves:
assign them once after the plan is approved and run the loop as RUN_CONTRACT.md § Holder
lanes states. Where the recipe declares `arr_policy`, each `record` is followed by
`ARR_POLICY.md` § Applying the policy, step 6, before the script runs again.

### 6. Review and report

Per `RUN_CONTRACT.md` § Review and report: `check-review` over the unreviewed checks, the
findings acted on without a ruling, then `check-report` with the plan's report title. A
scoped run's review and report are held to the families it ran (`run.json.plan.scope`), and the deliverable names the families the
user left out.

### 7. Close

The deliverables are `out/workbook.xlsx` and `out/report.pptx`; the report wave's preview
put them on screen as rendered cards. `out/RUN_SUMMARY.md` is in that wave's working
bundle. Point at all three. Hand
over the run archive `out/run_sync.tar.gz` per `RUN_CONTRACT.md` § Bringing the run home;
extracted under the user's result root it lands at `<short_name>.<datetime>` with
`sync.json` carrying the run's session ids. Relay the exception schedule and the open
items, each with its amount, what closes it and who owns it, and the coverage the run
achieved; on a scoped run, also the steps the user left out. Invite instructions: a directed fix re-runs the owning check and reseals the
report.
