---
name: stock-based-compensation
description: >-
  Test stock-based compensation under ASC 718: read your files, draft a plan for your
  confirmation, prove every award granted is on the books, support each grant date and
  grant-date fair value against the valuation in force, recompute every award's expense
  under your elections with its forfeitures, conditions and modifications, roll the
  awards outstanding forward, and hand you the walk from reported to supported expense
  with the stock compensation note's figures, every figure re-performable. Invoke when
  the user asks to check, recompute or audit-ready their stock-based compensation, option
  expense, RSUs, grant-date values, cheap stock or option rollforward.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `stock-based-compensation`: fetch
it with `get_recipe_for_countz_analysis(recipe="stock-based-compensation")` on the
`countz` server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the
served bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `stock-based-compensation`: the run directory is
`<output_root>/stock-based-compensation-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for more than the equity administration system's export.** The run tests the register against the
board consents, the award agreements, the HR roster with termination dates, the
valuations of the common stock with their option-pricing memos, and the policy memo that
states the elections. Ask for them, and for the months after the period end, in the same
pass. Their absence degrades families; it does not stop the run.
