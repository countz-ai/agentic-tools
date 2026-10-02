---
name: cash
description: >-
  Prove out the company's cash and cash equivalents before the auditors arrive: read
  your files, draft an account-by-account plan for your confirmation, rule every account
  against the definition, prove each account's activity and balance to the bank's own
  record, test the period end, and hand you the walk from recorded cash to cash as
  substantiated with the exceptions and open items, every figure re-performable. Invoke
  when the user asks to check, substantiate, prove out, or audit-ready their cash
  balances, cash equivalents, restricted cash, bank reconciliations, proof of cash, or
  bank activity.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `cash-substantiation`: fetch it with
`get_recipe_for_countz_analysis(recipe="cash-substantiation")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`cash`: the run directory is `<output_root>/cash-<company>.<YYYYMMDD-HHMMSS>`.
