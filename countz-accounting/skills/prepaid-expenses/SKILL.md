---
name: prepaid-expenses
description: >-
  Substantiate prepaid expenses, deposits and other receivables before a first audit:
  read your files, draft a plan, roll every item forward from
  opening through additions and amortization to closing, trace each addition to its
  invoice or contract and service period, recompute the amortization, find expense
  booked outside the period it covers, test deposits and other receivables against
  receipts after the period end, and hand you the walk from recorded to supported
  balances, every figure re-performable. Invoke when the user asks to review or
  audit-ready prepaid expenses, a prepaid schedule or amortization, security deposits,
  other current or noncurrent assets, or other receivables such as employee advances.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" prepaid-expenses; fi
```

You are the relay for a plan-driven run. Your recipe is `prepaid-expenses`: fetch it
with `get_recipe_for_countz_analysis(recipe="prepaid-expenses")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `prepaid-expenses`: the run directory is
`<output_root>/prepaid-expenses-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
