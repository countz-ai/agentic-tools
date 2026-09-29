---
name: revenue-analysis
description: >-
  Analyze the company's recurring revenue from its own billing, contract, customer and
  ledger records: build a cleansed customer cube at customer, product and month grain,
  compute ARR independently on a stated definition and trend it by product, segment,
  channel, region, contract term and every other dimension the data carries, measure
  gross and net retention, renewal, new, expansion, contraction and churn, present
  acquired revenue pro forma and separate organic from acquired growth, name the
  one-time events that break comparability, re-perform management's KPIs with every
  difference attributed, and reconcile ARR to GAAP revenue — every figure re-performable
  from the cube. Invoke when the user asks for an ARR or recurring-revenue analysis, a
  quality of revenue review, net or gross retention, churn, a customer cube, an ARR
  bridge, or ARR reconciled to GAAP revenue.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `revenue-analysis`: fetch it with
`get_recipe_for_countz_analysis(recipe="revenue-analysis")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `revenue-analysis`: the run directory is
`<output_root>/revenue-analysis-<company>.<YYYYMMDD-HHMMSS>`.
