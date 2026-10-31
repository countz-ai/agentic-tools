---
name: analyze
description: >-
  Run an accounting analysis over the company's own records, or list what
  countz runs: the ask, in the user's words, is matched to the server's
  catalog of analyses (examples: quality of earnings, cash, revenue, receivables and
  collections, leases, debt, payroll, income taxes, equity, ARR), or a recipe is authored
  from it. Invoke when the user asks for an accounting, audit-readiness or diligence
  analysis of their records, names one (examples: a QoE, a DSO diagnostic, an ARR
  bridge), asks what countz can do or which analysis fits their question, or
  says "use countz to ..." followed by what they want analyzed.
argument-hint: "[what you want analyzed]"
context: inline
---

What the user typed after `/countz:analyze` decides what you do. Invoked without the slash
command, take the ask from the message that invoked you.

- **Nothing**, or a question about what countz runs → § What countz
  runs.
- **Anything else** is the ask → § Run the analysis the ask describes. Read the whole
  text for the analysis it names, wherever the name stands: `/countz:analyze qoe ~/acme` and
  `/countz:analyze run a qoe analysis on ~/acme` are the same ask.

## What countz runs

Read no file first. Call `get_countz_config` on the `countz` server, once. It returns
`catalog_yaml`, one entry per analysis with `name`, `description` and `aliases`.

Then send one message: the table and the line below, as written, and under them the
analyses as a table of their own, one row per catalog entry: `/countz:analyze <name>` and the
entry's `description` in one line. If the call is not available or fails, send the table
and the line and add one line: "Server catalog not reachable: sign in to Countz to see
the analyses it runs."

| skill | what it does |
|---|---|
| `/create-arr-policy` | Settle the company's ARR policy: the four positions, the conventions and all 31 decisions that fix how annual recurring revenue is computed. Reads the company's existing ARR rules from its documents or a policy file, asks only the questions they leave open, shows the whole policy for approval and saves it. |
| `/drilldown` | Drill down into a result of a finished run and explain it in accounting terms: what the item is, what it rests on, and why it is worth attention. Re-performs the statements behind it and queries the run for the evidence around it first. |
| `/recon` | Reconcile two or more data sources: explain the difference between related records — a general ledger cash account to a bank statement, a payables ledger to a supplier statement — through item matching and classified reconciling items. |
| `/reperform` | Re-perform a result of a finished run step by step: from the data-room file, through each statement and query, to the result, with the data, the logic and the SQL to copy at each step. |
| `/tieout` | Tie out two or more data sources: establish whether records of the same quantity agree — a general ledger to a trial balance, a sub-ledger to its control account, a schedule to its detail — and analyze what does not. |

Run any analysis with `/countz:analyze <the analysis> <your files>`, or `/countz:analyze` followed by what you want analyzed in your own words.

Close by asking which one the user wants and what files they have. Every analysis
drafts its plan from your files first and runs nothing until you confirm it.

## Run the analysis the ask describes

Sign in first (`${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md § Sign in first`):
`get_countz_config` returns `catalog_yaml`, one entry per analysis with `name`,
`description` and `aliases`. Never carry a list of analyses of your own: the catalog is
fetched on every run, so what the server added since the plugin was installed is there.

**Match the ask against the catalog.** Read each entry's `description` and `aliases`.
The ask matches an entry when it names that analysis anywhere in its text: by name, by
an alias, or by describing the entry's stated objective. **An alias
hit is a match.** The ask does not match when it names a different analysis; a framework
it names (IFRS 16) does not change the match. A related analysis the catalog does not
carry is a miss, never a near-match: a false match runs the wrong analysis, a miss
authors the right one. Say which entry matched and why in one line, or that none did.
Then:

- **A match**: you run it, as below.
- **No match, and the ask is what a skill in the table under
  § What countz runs does**
  (examples: a drilldown or a re-performance of a finished run's result, an ARR policy
  to settle): invoke that skill with the Skill tool, the ask verbatim as its arguments. You do
  nothing more.
- **No match, and the ask is a single check kind on its own** (examples: a bank
  reconciliation, a trial-balance tie): invoke `recon` (the difference between two related records) or
  `tieout` (whether records of the same quantity agree) the same way.
- **Any other miss**: you run it, as below.

### Relay a catalog match or a miss

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz $(ls -td "$HOME"/.claude/plugins/cache/*/countz/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; cat "$R/reference/RUN_CONTRACT.md"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Running a recipe"; fi
```

You are the relay for a plan-driven run. You do no analysis and you open no client file.
On a match, the run directory is named after the matched recipe. On a miss, it is named
after this skill: register with `--skill analyze`, and the run directory is
`<output_root>/analyze-<company>.<YYYYMMDD-HHMMSS>`.

On a match, the relay procedure runs from its § 1 with the matched entry's `name` as the
recipe's name; its § 2 collects the ask in the user's words as `instructions`.
`PLAYBOOK_RECIPES.md § Fetch the recipe and register` runs as:

1. **On a match**, run `scripts/bundled_recipe.py <the entry's name>` first and pin the
   bundled copy when it prints one (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`).
   Otherwise call `get_recipe_for_countz_analysis(recipe=<the entry's name>)` and
   register with `--recipe-result <the saved result>` where the host saved the result to
   a file, else write `recipe_markdown` to a file and register with
   `--recipe <that file> --recipe-version <recipe_version>`
   (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`).
2. **On a miss**, scrub the ask before anything crosses, under
   `${CLAUDE_PLUGIN_ROOT}/reference/SCRUB.md` (read it whole). Register the run first
   (the registration in `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, with
   `--skill analyze` in place of `--recipe`). Then two separate invocations of the `countz:scrubber` agent
   (the Agent tool, `subagent_type: countz:scrubber`, a fresh agent each time,
   the brief stating the mode) — no script decides what identifies the company:

   1. **Scrub.** Dispatch the scrubber with `mode: scrub`, the ask verbatim (from
      `instructions`), and the registration from `run.json`: `inputs.company`, every
      source's `name`, and any entity or alias the user named. It returns `SEND:` (the
      description) and `REMOVED:` (one line per removal, class and replacement).
   2. **Blind check.** Dispatch the scrubber again, as a new invocation, with
      `mode: blind` and **only the `SEND` text** — never the ask, the registration or the
      removal list. It returns `VERDICT: clean` or `VERDICT: flagged` with its flags.
   3. On `flagged`, repeat 1 passing the flags, then 2 on the new text. After three
      rounds without `clean`, send nothing: say so in one line and go to `create-recipe`
      (below) with the full ask, which never leaves the machine.
   4. Record it — the removal lists, the verdicts and the text sent:

      ```
      uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py record-scrub <run_dir> --json @<run_dir>/scrub-draft.json
      ```

      where the file (written with the Write tool, so no quoting touches the text) holds `{"send": "<SEND text>", "rounds": [{"removed": [{"category": "...", "replacement": "..."}], "verdict": "clean|flagged", "flags": [{"category": "...", "where": "..."}]}, ...]}`.
      It refuses unless the last round is `clean`, writes `scrub.json`, deletes the draft,
      and prints `SEND:` — the exact text.

   **Tell, then send.** Put the `SEND` text to the user in one line — *"Nothing in the
   catalog covers this. I'm sending Countz this description and nothing else, so it can
   serve or plan a recipe for it: `<SEND text>`"* — then call
   `create_countz_playbook_recipe(ask=<SEND text>)` with the bytes `record-scrub`
   printed. The server matches once more against its aliases.
   - `match` is `alias`: continue as step 1, with the body it returned.
   - `match` is `not_found`: dispatch `create-recipe` (below). The full ask stays in
     `run.json.inputs.params.instructions`; only the `SEND` text crossed.

### Authoring the recipe

`create-recipe` is a fork: it reads the registered sources under the bounded-read rules
and cannot ask the user anything, so it runs twice, exactly as `check-plan` runs again
on `revise=`.

1. **Draft stage.** `run_state.py dispatch <run_dir> --step recipe --args '<one-line JSON>'`
   with `ask=` (the user's ask verbatim, from `instructions`), `catalog=` (the
   `catalog_yaml` you fetched), then the plain Skill call. It returns the questions it
   needs answered: the objective in one sentence, the population, the source classes it
   found, the grain the data supports, and what the ask leaves open. `record`.
2. **Relay.** Put those questions to the user, in its words, and collect the answers.
3. **Author stage.** Dispatch `create-recipe` again on a new seq with the same arguments
   plus `answers=` (the user's answers, verbatim). It writes
   `<run_dir>/recipes/<name>.md`, runs `scripts/validate_recipe.py` over it, and ends
   `blocked` rather than hand the plan a malformed recipe. `record`, then pin the file:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID} \
       --sources '[]' --recipe <run_dir>/recipes/<name>.md
   ```

   Show the recipe to the user (`preview.py` names it) before the plan step. A generated
   recipe belongs to this run: a later run over the same analysis generates again.
4. **What to run.** Put the generated recipe's steps to the user as
   `PLAYBOOK_RECIPES.md § Ask what to run` does, over the pinned file, and register the
   picks with `setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID} --sources '[]'
   --scope <picks>` (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, *The
   scope*).

Where the pinned recipe declares `arr_policy`, served or generated, settle it first
(`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, *The ARR policy*). Then
`PLAYBOOK_RECIPES.md § Plan`, with `recipe=` the pinned path and `instructions=` the
ask, and everything after it unchanged.
