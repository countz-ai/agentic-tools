---
name: fixed-assets
description: >-
  Substantiate property and equipment and capitalized software before a first audit:
  read your files, draft a plan for your confirmation, roll every asset class forward,
  trace each addition to its invoice and placed-in-service date, rule each disposal,
  recompute depreciation and amortization from your policy's lives and methods, test
  the capitalization policy both ways, trace capitalized software labor to payroll and
  project records, and hand you the walk from recorded to supported balances, every
  figure re-performable. Invoke when the user asks to review or audit-ready fixed
  assets, property and equipment, the fixed asset register or depreciation, leasehold
  improvements, construction in progress, intangible assets, the capitalization policy,
  or capitalized internal-use or hosting implementation software costs.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `fixed-assets`: fetch it
with `get_recipe_for_countz_analysis(recipe="fixed-assets")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `fixed-assets`: the run directory is
`<output_root>/fixed-assets-<company>.<YYYYMMDD-HHMMSS>`.
