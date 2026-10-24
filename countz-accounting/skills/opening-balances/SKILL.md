---
name: opening-balances
description: >-
  Establish before a first audit that each period opens on the balances the prior period
  closed on: read your files, draft a plan, tie each opening trial
  balance to the prior trial balance, financial statements and tax returns as last
  reported and across any system change, rule every adjustment posted between a close
  and the next opening, a cash or tax basis to GAAP conversion included, as an error
  correction or a policy change, roll the accumulated deficit across the periods
  presented, and hand you the differences and open items, every figure re-performable.
  Invoke when the user asks to check or audit-ready opening balances, tie the old
  system's balances to the new one's, review a conversion to GAAP accrual, or roll
  retained earnings or the accumulated deficit forward.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" opening-balances; fi
```

You are the relay for a plan-driven run. Your recipe is `opening-balances`: fetch it
with `get_recipe_for_countz_analysis(recipe="opening-balances")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `opening-balances`: the run directory is
`<output_root>/opening-balances-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
