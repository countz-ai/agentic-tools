---
name: stock-based-compensation
description: >-
  Test stock-based compensation under ASC 718: read your files, draft a plan, prove every award granted is on the books, support each grant date and
  grant-date fair value against the valuation in force, recompute every award's expense
  under your elections with its forfeitures, conditions and modifications, roll the
  awards outstanding forward, and hand you the walk from reported to supported expense
  with the stock compensation note's figures, every figure re-performable. Invoke when
  the user asks to check, recompute or audit-ready their stock-based compensation, option
  expense, RSUs, grant-date values, cheap stock or option rollforward.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" stock-based-compensation; fi
```

You are the relay for a plan-driven run. Your recipe is `stock-based-compensation`: fetch
it with `get_recipe_for_countz_analysis(recipe="stock-based-compensation")` on the
`countz` server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the
served bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `stock-based-compensation`: the run directory is
`<output_root>/stock-based-compensation-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
