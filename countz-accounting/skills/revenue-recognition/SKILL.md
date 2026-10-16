---
name: revenue-recognition
description: >-
  Test whether the company's revenue is recognized under ASC 606 in the right period and
  at the right amount, from its own records: tie the revenue line to its billing and
  contract detail, reconcile billings to revenue through the contract balances, place
  every revenue item in the period its performance obligation was satisfied, test the
  period-end cutoff, trace the deferred and unbilled balances, re-apply the five steps
  to the contracts that carry the revenue and the risk, and hand the reader reported
  revenue walked to revenue as supported — every adjustment an entry with its
  counter-account, every figure re-performable. Invoke when the user asks to check,
  test or audit-ready revenue recognition or ASC 606 compliance, revenue cutoff,
  deferred or unbilled revenue, or whether revenue sits in the right period.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=$(for d in "${CLAUDE_PLUGIN_ROOT}" "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && echo "${d%/}" && break; done); echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" revenue-recognition
```

`PLUGIN_ROOT=` names this plugin's folder: wherever these documents write
`${CLAUDE_PLUGIN_ROOT}`, use that path. Never search the filesystem for it. If the line
names no path, run `find "$HOME/.claude" -maxdepth 7 -path '*/countz-accounting/scripts/section.py'`
once. Act on the sign-in result as § Sign in first says. Then ask what to run as
§ Ask what to run says: its recipe is the bundled copy the last line names, or, on
`NONE`, the one the server serves. Once the user has answered, read
`<PLUGIN_ROOT>/reference/RUN_CONTRACT.md` whole and the rest of the relay procedure
(`section.py PLAYBOOK_RECIPES.md "Running a recipe"`), and go on from its § 2.

You are the relay for a plan-driven run. Your recipe is `revenue-recognition`: fetch it with
`get_recipe_for_countz_analysis(recipe="revenue-recognition")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`revenue-recognition`: the run directory is `<output_root>/revenue-recognition-<company>.<YYYYMMDD-HHMMSS>`.
