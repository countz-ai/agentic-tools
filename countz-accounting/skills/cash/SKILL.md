---
name: cash
description: >-
  Prove out the company's cash and cash equivalents before the auditors arrive: read
  your files, draft an account-by-account plan, rule every account
  against the definition, prove each account's activity and balance to the bank's own
  record, test the period end, and hand you the walk from recorded cash to cash as
  substantiated with the exceptions and open items, every figure re-performable. Invoke
  when the user asks to check, substantiate, prove out, or audit-ready their cash
  balances, cash equivalents, restricted cash, bank reconciliations, proof of cash, or
  bank activity.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=$(for d in "${CLAUDE_PLUGIN_ROOT}" "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && echo "${d%/}" && break; done); echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" cash-substantiation
```

`PLUGIN_ROOT=` names this plugin's folder: wherever these documents write
`${CLAUDE_PLUGIN_ROOT}`, use that path. Never search the filesystem for it. If the line
names no path, run `find "$HOME/.claude" -maxdepth 7 -path '*/countz-accounting/scripts/section.py'`
once. Act on the sign-in result as § Sign in first says. Then ask what to run as
§ Ask what to run says: its recipe is the bundled copy the last line names, or, on
`NONE`, the one the server serves. Once the user has answered, read
`<PLUGIN_ROOT>/reference/RUN_CONTRACT.md` whole and the rest of the relay procedure
(`section.py PLAYBOOK_RECIPES.md "Running a recipe"`), and go on from its § 2.

You are the relay for a plan-driven run. Your recipe is `cash-substantiation`: fetch it with
`get_recipe_for_countz_analysis(recipe="cash-substantiation")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`cash`: the run directory is `<output_root>/cash-<company>.<YYYYMMDD-HHMMSS>`.
