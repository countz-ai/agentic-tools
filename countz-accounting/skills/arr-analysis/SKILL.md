---
name: arr-analysis
description: >-
  Analyze the company's recurring revenue from its own billing, contract, customer and
  ledger records: build a cleansed customer cube at customer, product and month grain,
  compute ARR independently on a stated definition and trend it by product, segment,
  channel, region, contract term and every other dimension the data carries, measure
  gross and net retention, renewal, new, expansion, contraction and churn, present
  acquired revenue pro forma and separate organic from acquired growth, name the
  one-time events that break comparability, re-perform management's KPIs with every
  difference attributed, and reconcile ARR to GAAP revenue — every figure re-performable
  from the cube. Invoke when the user asks for an ARR or recurring-revenue analysis, a
  quality of revenue review, net or gross retention, churn, a customer cube, an ARR
  bridge, or ARR reconciled to GAAP revenue.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" arr-analysis
```

`PLUGIN_ROOT=` names this plugin's folder: wherever these documents write
`${CLAUDE_PLUGIN_ROOT}`, use that path. The command already searches `~/.claude/plugins`
when the known places miss; search nowhere else. If the line names no path, tell the user
in one line that this plugin's files are not installed in the session, and stop. Act on the sign-in result as § Sign in first says. Then ask what to run as
§ Ask what to run says: its recipe is the bundled copy the last line names, or, on
`NONE`, the one the server serves. Once the user has answered, read
`<PLUGIN_ROOT>/reference/RUN_CONTRACT.md` whole and the rest of the relay procedure
(`section.py PLAYBOOK_RECIPES.md "Running a recipe"`), and go on from its § 2.

You are the relay for a plan-driven run. Your recipe is `arr-analysis`: fetch it with
`get_recipe_for_countz_analysis(recipe="arr-analysis")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `arr-analysis`: the run directory is
`<output_root>/arr-analysis-<company>.<YYYYMMDD-HHMMSS>`.
