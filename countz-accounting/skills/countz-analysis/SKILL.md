---
name: countz-analysis
description: >-
  Run an accounting analysis you describe in your own words backed by the Countz Accounting platform.
  You confirm the plan before anything runs. Invoke when the user says "use
  countz to do analysis: ..." followed by what they want analyzed, or asks for an
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
3. **On a match**, run `scripts/bundled_recipe.py <the entry's name>` first and pin the
   bundled copy when it prints one (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`).
   Otherwise call `get_recipe_for_countz_analysis(recipe=<the entry's name>)` and
   continue as a named shim does: write `recipe_markdown` to a file and register with
   `--recipe <that file> --recipe-version <recipe_version>`
   (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`).
4. **On a miss**, scrub the ask before anything crosses, under
   `${CLAUDE_PLUGIN_ROOT}/reference/SCRUB.md` (read it whole). Register the run first
   (the registration in `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, without
   `--recipe`). Then two separate invocations of the `countz-accounting:scrubber` agent
   (the Agent tool, `subagent_type: countz-accounting:scrubber`, a fresh agent each time,
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
      python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py record-scrub <run_dir> --json @<run_dir>/scrub-draft.json
      ```

      where the file (written with the Write tool, so no quoting touches the text) holds `{"send": "<SEND text>", "rounds": [{"removed": [{"category": "...", "replacement": "..."}], "verdict": "clean|flagged", "flags": [{"category": "...", "where": "..."}]}, ...]}`.
      It refuses unless the last round is `clean`, writes `scrub.json`, deletes the draft,
      and prints `SEND:` — the exact text.

   **Tell, then send.** Put the `SEND` text to the user in one line — *"Nothing in the
   catalog covers this. I'm sending Countz this description and nothing else, so it can
   serve or plan a recipe for it: `<SEND text>`"* — then call
   `get_recipe_for_countz_analysis(ask=<SEND text>)`, naming no recipe, with the bytes
   `record-scrub` printed. The server matches once more against its aliases.
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

Where the pinned recipe declares `arr_policy`, served or generated, settle it first
(`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, *The ARR policy*). Then
`PLAYBOOK_RECIPES.md § Plan`, with `recipe=` the pinned path and `instructions=` the
ask, and everything after it unchanged.
