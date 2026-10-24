---
name: going-concern
description: >-
  Prepare the figures for the going concern evaluation under ASC 205-40 before a first
  audit: read your files, draft a plan, schedule every obligation due
  in the year after the statements are issued, tie your forecast to the bank, re-perform it
  without the plans not yet implemented and project each covenant on it, measure earlier
  forecasts against actual results, list the conditions and events, test each of your plans
  against its evidence, and hand you the walk from your forecast to liquidity headroom as
  corrected, before and after the plans, with the disclosure figures. The substantial doubt
  conclusion stays with you and your auditor. Invoke when the user asks about going
  concern, substantial doubt, cash runway, burn rate or liquidity before an audit.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" going-concern; fi
```

You are the relay for a plan-driven run. Your recipe is `going-concern`: fetch it
with `get_recipe_for_countz_analysis(recipe="going-concern")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `going-concern`: the run directory is
`<output_root>/going-concern-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
