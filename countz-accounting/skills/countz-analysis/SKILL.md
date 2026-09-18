---
name: countz-analysis
description: >-
  Run an accounting analysis you describe in your own words backed by the Countz Accounting platform.
  You confirm the plan before anything runs. Invoke when the user says "use
  countz to do analysis: ..." followed by what they want analysed, or asks for an
  analysis no named skill covers.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run whose recipe is not fixed in advance. You do no
analysis and you open no client file. Your `--skill` is `countz-analysis`: the run
directory is `<output_root>/countz-analysis-<company>.<YYYYMMDD-HHMMSS>`.

The relay procedure's § 1 collects the ask in the user's words as `instructions`. What
differs from a named shim is `PLAYBOOK_RECIPES.md § Fetch the recipe and register`,
which for this skill runs as:

1. **Read the catalog** — the `catalog_yaml` that `get_countz_config` returned at sign-in
   (`RUN_CONTRACT.md § Sign in first`). Never carry a list of analyses of your own — the
   catalog is fetched on every run, so what the server added since the plugin was
   installed is there.
2. **Match the ask against the catalog.** Read each entry's `description` and
   `aliases`. The ask matches an entry when it names that analysis — by name, by an
   alias, or by describing the entry's stated objective. **An alias hit is a match.** The
   ask does not match when it names a different analysis, a different accounting standard
   (IFRS 16 is not the ASC 842 entry), or a single check kind on its own — a bank
   reconciliation, a trial-balance tie — which the `recon` and `tieout` skills run. A
   related analysis the catalog does not carry is a miss, never a near-match: a false
   match runs the wrong analysis, a miss authors the right one. Say which entry matched
   and why in one line, or that none did.
3. **On a match**, call `get_recipe_for_countz_analysis(recipe=<the entry's name>)` and
   continue as a named shim does: write `recipe_markdown` to a file and register with
   `--recipe <that file> --recipe-version <recipe_version>`
   (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`).
4. **On a miss**, scrub the ask before anything crosses. Rewrite it so it names the
   analysis and nothing of the company's — no company name, no file name, no figure, no
   account number, no person; periods may stay (`FY2025`, `Q3`, `March 2026`). Register
   the run first (the registration in `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, without `--recipe`), then run the gate:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/scrub_ask.py <run_dir> --ask "<the scrubbed ask>"
   ```

   A `REFUSED:` line names what is still in it; rewrite and run the gate again. The
   `SEND:` line is the exact text that will cross: put it to the user in one line —
   *"Nothing in the catalog covers this. I'll send Countz this description and nothing
   else, so it can serve or plan a recipe for it: `<SEND text>`"* — then call
   `get_recipe_for_countz_analysis(ask=<SEND text>)`, naming no recipe. The server
   matches once more against its aliases.
   - `match` is `alias`: continue as step 3, with the body it returned.
   - `match` is `not_found`: dispatch `create-recipe` (below). The full ask stays in
     `run.json.inputs.params.instructions`; only the `SEND` text crossed.

## Authoring the recipe

`create-recipe` is a fork: it reads the registered sources under the bounded-read rules
and cannot ask the user anything, so it runs twice, exactly as `check-plan` runs again
on `revise=`.

1. **Draft pass.** `run_state.py dispatch <run_dir> --step recipe --args '<one-line JSON>'`
   with `ask=` (the user's ask verbatim, from `instructions`), `catalog=` (the
   `catalog_yaml` you fetched), then the plain Skill call. It returns the questions it
   needs answered: the objective in one sentence, the population, the source classes it
   found, the grain the data supports, and what the ask leaves open. `record`.
2. **Relay.** Put those questions to the user, in its words, and collect the answers.
3. **Author pass.** Dispatch `create-recipe` again on a new seq with the same arguments
   plus `answers=` (the user's answers, verbatim). It writes
   `<run_dir>/recipes/<name>.md`, runs `scripts/validate_recipe.py` over it, and ends
   `blocked` rather than hand the plan a malformed recipe. `record`, then pin the file:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID} \
       --sources '[]' --recipe <run_dir>/recipes/<name>.md
   ```

   Show the recipe to the user (`preview.py` names it) before the plan step. A generated
   recipe belongs to this run: a later run over the same analysis generates again.

Then `PLAYBOOK_RECIPES.md § Plan`, with `recipe=` the pinned path and `instructions=`
the ask, and everything after it unchanged.
