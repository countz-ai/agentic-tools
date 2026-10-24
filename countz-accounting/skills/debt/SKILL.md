---
name: debt
description: >-
  Substantiate borrowings and covenant compliance before a first audit: read your files,
  draft a plan, roll principal forward against the loan agreements
  and the lender statements, recompute interest, accrued interest and the effective
  interest amortization of discounts, issuance costs and end-of-term fees, rule each
  amendment, classify each borrowing current or noncurrent with every breach and waiver,
  compute each covenant the way the agreement defines it, schedule the maturities, and
  hand you the walk from recorded to supported debt, every figure re-performable. Invoke
  when the user asks to review or audit-ready debt, borrowings, a term loan, venture
  debt, a revolving line or notes payable, interest expense or accrued interest on a
  loan, debt issuance costs or an end-of-term fee, debt classification, a loan
  amendment, or covenant compliance.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" debt; fi
```

You are the relay for a plan-driven run. Your recipe is `debt`: fetch it
with `get_recipe_for_countz_analysis(recipe="debt")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `debt`: the run directory is
`<output_root>/debt-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
