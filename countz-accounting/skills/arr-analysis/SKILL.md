---
name: arr-analysis
description: >-
  Calculate and analyze the company's own ARR from first principles, for its operators
  and board, from its billing, contract, customer and ledger records: build a cleansed
  customer cube at customer, product and month grain, compute ARR on the company's
  approved definition and trend it by product, segment, channel, region, contract term
  and every other dimension the data carries, explain its movement through new,
  expansion, contraction and churn, measure gross, net and logo retention, renewal and
  cohorts, separate organic from acquired growth, show what the revenue depends on and
  what drives growth and retention, with the ARR at stake, and reconcile ARR to GAAP revenue — every
  figure re-performable from the cube. Invoke when the user asks to calculate ARR, for an
  ARR or recurring-revenue analysis, net or gross retention, churn, cohorts, a customer
  cube, an ARR bridge, or ARR reconciled to GAAP revenue.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `arr-analysis`: fetch it with
`get_recipe_for_countz_analysis(recipe="arr-analysis")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `arr-analysis`: the run directory is
`<output_root>/arr-analysis-<company>.<YYYYMMDD-HHMMSS>`.
