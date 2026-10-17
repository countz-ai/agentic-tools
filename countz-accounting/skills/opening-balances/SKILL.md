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

**Ask for what each prior period reported.** The run compares the ledger with every
record the company handed a reader: the trial balances it delivered, the financial
statements it issued with any accountant's report, and the tax returns as filed. Ask for
them with the ledger, for the periods presented and the year before the earliest one, and
in the same pass for the ledger's audit log, any system migration's mapping and cutover
trial balances, the outside accountant's adjusting entries, the policy memos and
management's list of known errors. Their absence degrades families; it does not stop the
run.

**Name the periods presented.** Ask which fiscal years the audit or the registration
statement will present. When you present the plan, show each period boundary with the
records as last reported for it, the basis each period's ledger shows, and the accounts
routed to their owners.
