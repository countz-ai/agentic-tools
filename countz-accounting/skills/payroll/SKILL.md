---
name: payroll
description: >-
  Reconcile payroll before a first audit: read your files, draft a plan, tie the payroll register to the ledger per pay run, component and
  income statement line, prove gross to net, agree the register to the federal and state
  payroll tax returns and the W-2 totals, recompute employer taxes, trace every
  remittance to the bank and the agencies' records, agree provider or PEO invoices to the
  ledger, test the people paid against the roster and contractor payments against the
  1099 totals, and hand you the walk from recorded to supported payroll cost, every
  figure re-performable. Invoke when the user asks to review, reconcile or audit-ready
  payroll, payroll taxes, Forms 941 or 940, W-2s, state payroll filings, a PEO, ghost
  employees, or contractor 1099s.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" payroll; fi
```

You are the relay for a plan-driven run. Your recipe is `payroll`: fetch it
with `get_recipe_for_countz_analysis(recipe="payroll")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `payroll`: the run directory is
`<output_root>/payroll-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
