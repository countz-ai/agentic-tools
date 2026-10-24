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

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" revenue-recognition; fi
```

You are the relay for a plan-driven run. Your recipe is `revenue-recognition`: fetch it with
`get_recipe_for_countz_analysis(recipe="revenue-recognition")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`revenue-recognition`: the run directory is `<output_root>/revenue-recognition-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
