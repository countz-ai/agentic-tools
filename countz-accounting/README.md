# countz-accounting

Interactive accounting checks over the user's own files, modeled on advisory-report's
md-driven engine: the skill and reference files ARE the procedure, and the agent inspects
the data before it binds anything. The user-facing skills run inline as the relay:
`tieout`, `recon`, `countz-analysis` (an analysis the user describes, matched
to the catalog or authored on the spot), and one plan-driven launcher per recipe under
`playbook-recipes/` — `ls` the directory for the recipes; each recipe's H1 says what its
run establishes, `catalog.yaml` beside them lists them for the server, and its shim is the
one inline skill under `skills/` that names it. The recipes are authored here and served
by the Countz connector at run time (`reference/RECIPE_FORMAT.md`); the package ships
none of them. The
workspace is registered mechanically (`scripts/setup_run.py`, no dispatch), every worker
step forks into an agent, and waves run as parallel sub-agents on dispatch briefs. A
plan-driven run: the planner reads the data room and drafts the check roster against the
recipe, the user confirms it, and the playbook engine executes it as a playbook —
`scripts/playbook_next.py` decides each wave mechanically, the `playbook-engine` agent
only when the script escalates.

Layout:

- `agents/` — `planner` (drafts the plan: reads the data room against a playbook recipe,
  writes the file index with relevance verdicts, the source profiles, and the
  definition; the one step that reads client files before any check runs), `worker`
  (runs one step), `critic` (adversarial review), `playbook-engine` (the playbook
  engine's escalation path: decides waves where `scripts/playbook_next.py` cannot,
  distills saved playbooks; opens no client file)
- `skills/` — the inline launchers (`tieout`, `recon`, `countz-analysis`,
  one shim per recipe), the internal inline relay `playbook`, plus the forked workers
  (`create-recipe`, `check-plan`, `check-extract`, `check-tie`, `check-recon`,
  `check-completeness`, `check-vouch`, `check-cutoff`, `check-analyze`, `check-review`,
  `check-report`, `playbook-next`, `playbook-save`)
- `reference/` — `CONDUCT.md` (the standing rules every agent reads first: the reader,
  the bounds on a figure, how to read a plugin document and a client file, the libraries,
  the events, the return value), `DOCTRINE.md` (the standard), `EVIDENCE.md` (citations,
  figures, the id namespace), `VALIDATION.md` (the whole review scope and the finding
  shape), `RUN_CONTRACT.md` (run dir,
  state, the step record, the per-wave duties), `PLAYBOOKS.md` (the playbook file format and
  library), `RECIPE_FORMAT.md` (what a recipe document must contain),
  `PLAYBOOK_RECIPES.md` (the rules every recipe runs under, and the relay
  procedure), `WORKBOOK.md` + `WORKBOOK_STYLE.md` (the workbook's one design:
  where things go, how cells look),
  `OBSERVABILITY.md` + `rates.json`
- Playbooks — user-saved ones land in `$HOME/.countz-accounting/playbooks/`; a
  plan-driven run drafts its own at `<run_dir>/plan/<name>.json`. New packaged capability
  is a playbook recipe (plus its shim skill — `reference/RECIPE_FORMAT.md`) composing the
  check kinds; a new kind is a worker skill — its procedure and its item tables — plus a `KINDS` row and
  params contract in `scripts/check_playbook.py`.
- `scripts/` — `setup_run.py` (mechanical workspace registration — mints the run
  directory `<skill>-<company>.<stamp>` with its `run.json`, or folds new sources into a
  run named by its path; the relay runs it, never a dispatch), `run_state.py` (the
  relay's pen for `run.json`: check registration, playbook binding, plan approval, wave
  dispatch, and classification with the one-retry rule — no agent hand-writes the state
  file), `check_playbook.py` (playbook validation + listing; the kind-to-skill
  map's one home), `playbook_next.py` (the mechanical wave decision — the relay runs it
  first; exit 3 `ESCALATE:` hands the one case to the agent), `preview.py` (names each new
  artifact with its tier — with debug mode off only the engagement preview, the plan, the
  workbook and the report deck; on, the findings as a rendered card too and everything
  else as one working-papers bundle per wave), `peek.py` (the bounded first look at any
  client file — index facts, sheet names and extents, the first rows, lines or page
  text; the planner's walk and every agent's first read go through it, and its row and
  line ceilings cannot be lifted), `check_workbook.py` + `check_prose.py` +
  `check_report.py` (deliverable gates), `recipe_format.py` + `validate_recipe.py` (the
  recipe shape contract and its CLI, the one gate on a generated recipe),
  `scrub_ask.py` (the gate on the one text that crosses to the connector), `section.py` (prints a named section of a
  plugin document, so a section-scoped citation costs its section and not its whole file),
  `wbkit.py` (the workbook kit every tab script imports — the style constants, the
  named styles and the block helpers, written once), `extract.py` (the `extract` step:
  parses the data-room files the plan's steps read into `<run_dir>/cache/` as typed
  parquet with a manifest, and the `read()` / `scan()` every consumer loads through),
  `evidence.py` (`span`: a citation measured on the file or the cache manifest — header,
  rows, columns, row count, control total — never typed),
  `build_report.py` (renders `out/report.pptx`
  from `report.yaml` and the sealed workbook — the deck mints nothing;
  `reference/REPORT.md`), `usage_report.py` (duration + estimated cost), `gather_debug.py`
  (debug mode: every wave copies the session transcripts into `<run_dir>/debug/` and
  distils the per-dispatch timeline, the offloaded tool results and the instruction
  snapshot — `reference/OBSERVABILITY.md` § 3)

No hooks: there is no unattended pipeline loop to re-enter — the user's session drives
every wave in-band.
