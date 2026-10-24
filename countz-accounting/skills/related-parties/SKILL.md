---
name: related-parties
description: >-
  Identify related parties and every transaction with them before a first audit: read
  your files, draft a plan, build the related-party list from the
  stock ledger, the minutes, the director and officer questionnaires and the affiliates'
  records, match your vendor, customer and employee masters against it, search the books,
  payroll, expense reports and the bank for every transaction and balance with a related
  party, agree each to its agreement and approval, and hand you the walk from the
  related-party figures you report to the figures the records support, with the
  disclosure figures. Invoke when the user asks to identify or review related parties,
  related-party transactions or balances, ASC 850 disclosures, conflicts of interest,
  entities under common control, or dealings with officers, directors, owners and
  affiliates.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" related-parties; fi
```

You are the relay for a plan-driven run. Your recipe is `related-parties`: fetch it
with `get_recipe_for_countz_analysis(recipe="related-parties")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `related-parties`: the run directory is
`<output_root>/related-parties-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
