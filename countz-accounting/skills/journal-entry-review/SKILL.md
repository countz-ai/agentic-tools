---
name: journal-entry-review
description: >-
  Review the period's journal entries and transactions for error and management
  override, from the company's own ledger: draft a plan, prove the
  entry population complete against the trial balance for every entity, screen every
  entry against criteria fixed before the results, test every selected entry against its
  support, and hand you the misstated and unsupported entries, the proposed correcting
  entries with their effect on pre-tax income, the patterns across entries and the
  holding balances to clear, every figure re-performable. Invoke when the user asks to
  review, test or scrub journal entries or transactions, test for management override,
  test 100% of the transactions in an account, find miscoded, uncategorized, duplicate or
  unusual entries, or clean up books someone else kept.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" journal-entry-review; fi
```

You are the relay for a plan-driven run. Your recipe is `journal-entry-review`: fetch it
with `get_recipe_for_countz_analysis(recipe="journal-entry-review")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `journal-entry-review`: the run directory is
`<output_root>/journal-entry-review-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
