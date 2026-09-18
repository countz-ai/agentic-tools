---
name: qoe
description: >-
  Build a quality-of-earnings EBITDA bridge from the company's own records: validate
  the revenue and cost figures it is built on, break the income statement down to ruled
  cost lines, identify every plausible addback from first principles, answer
  management's proposed adjustments, and walk EBIT through reported EBITDA,
  management's adjusted view where one exists, and diligence-adjusted EBITDA to
  pro-forma — argued sell-side unless the user declares a buy-side engagement, with every
  figure re-performable. Invoke when the user asks for a QoE or quality of earnings, an
  EBITDA bridge, adjusted or normalized EBITDA, or an addback analysis.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `quality-of-earnings`: fetch it with
`get_recipe_for_countz_analysis(recipe="quality-of-earnings")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`qoe`: the run directory is `<output_root>/qoe-<company>.<YYYYMMDD-HHMMSS>`.

Put `perspective` to the user with the rest of the collection. Where they do not choose,
take `sell_side`: the reader is the company's own executives. `buy_side` is the user's to
declare; do not read it off the data room (`RUN_CONTRACT.md` § Parameters).
