---
name: stockholders-equity
description: >-
  Substantiate stockholders' equity and the instruments the company issued to raise
  capital: read your files, draft a plan, tie the capitalization
  table to the stock ledger, the approvals and the charter, trace every SAFE, note,
  warrant and preferred series to its agreement, classify each as a liability, temporary
  equity or permanent equity, re-perform each financing, conversion and remeasurement,
  and hand you the walk from reported to supported equity with the fully diluted
  capitalization, every figure re-performable. Invoke when the user asks to check,
  reconcile or audit-ready their cap table, equity, SAFEs, convertible notes, warrants
  or preferred stock, or asks whether an instrument is a liability or equity.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" stockholders-equity; fi
```

You are the relay for a plan-driven run. Your recipe is `stockholders-equity`:
fetch it with `get_recipe_for_countz_analysis(recipe="stockholders-equity")`
on the `countz` server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin
the served bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `stockholders-equity`: the run directory is
`<output_root>/stockholders-equity-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the legal record with the books.** The run supports share counts with the stock
ledger, the charter and every amendment, the board and stockholder consents, and the
signed SAFEs, notes, warrants, purchase agreements and side letters. Ask for them, and
for the valuation reports and the months after the period end, in the same pass. Their
absence degrades families; it does not stop the run.
