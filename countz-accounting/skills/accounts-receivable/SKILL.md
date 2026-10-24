---
name: accounts-receivable
description: >-
  Substantiate trade receivables and the allowance for credit losses before a first
  audit: read your files, draft a plan, tie the aging to the ledger,
  apply the cash received after the period end to each open item, vouch the items it does
  not clear to the invoice and the evidence of delivery, test the credits and write-offs
  after the period end, reclassify credit balances, recompute the allowance under ASC 326
  and back-test it against the write-offs that followed, list the confirmations for the
  auditor, and hand you the walk from recorded to supported receivables, every figure
  re-performable. Invoke when the user asks to review or audit-ready accounts receivable,
  the aging, unbilled receivables, the allowance for credit losses or doubtful accounts,
  bad debt, write-offs, customer credit balances, or receivable confirmations.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" accounts-receivable; fi
```

You are the relay for a plan-driven run. Your recipe is `accounts-receivable`: fetch it
with `get_recipe_for_countz_analysis(recipe="accounts-receivable")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `accounts-receivable`: the run directory is
`<output_root>/accounts-receivable-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
