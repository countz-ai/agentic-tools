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

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `revenue-recognition`: fetch it with
`get_recipe_for_countz_analysis(recipe="revenue-recognition")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`revenue-recognition`: the run directory is `<output_root>/revenue-recognition-<company>.<YYYYMMDD-HHMMSS>`.
