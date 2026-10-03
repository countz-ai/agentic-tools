---
name: unrecorded-liabilities
description: >-
  Search for unrecorded liabilities and test accruals at a period end: read your files,
  draft a plan for your confirmation, trace the payments and invoices after the period
  end, the goods received not invoiced and the obligations in contracts, minutes and legal
  invoices back to when each was incurred, test cutoff, state and re-perform each
  accrual's method and trace its reversal, and hand you the walk from recorded to
  supported payables and accrued liabilities with each correction's effect on pre-tax
  income, every figure re-performable. Invoke when the user asks to search for unrecorded
  liabilities, test accruals or accrued expenses, check payables completeness or expense
  cutoff, trace subsequent payments, or confirm the accruals reversed.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `unrecorded-liabilities`: fetch it
with `get_recipe_for_countz_analysis(recipe="unrecorded-liabilities")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `unrecorded-liabilities`: the run directory is
`<output_root>/unrecorded-liabilities-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the months after the period end.** The search reads the bank statements, the
payment registers and the invoices received after the period end, the card statements,
the received-not-invoiced report, vendor statements, the accrual schedule with its
workings, the prior period end's accrual schedule, contracts, legal invoices and board
minutes. Ask for them in the same pass. Their absence degrades families; it does not stop
the run.

**Collect `search_window`, `search_threshold` and `stale_accrual_days`.** Ask in plain
words, one option at a time, each with what it controls, its default and what changing it
does. Use these sentences or your own equivalent:

- **Search window**: how long after year end we look at payments and incoming invoices
  for bills that belong to the year. Default: 60 days, or longer if the company usually
  takes longer than that to pay its bills. A longer window finds bills paid late and
  takes longer to run; a shorter one misses them.
- **Tracing threshold**: payments and invoices at or above this amount are each traced
  to the bill behind them; a random selection of smaller ones is traced too. Default: set
  so the traced items cover at least 80% of the dollars, and never above 75% of
  materiality. A lower amount traces more items and takes longer; a higher one leaves
  more dollars untraced.
- **Stale accrual age**: an accrual with no invoice, payment or true-up behind it after
  this many days is tested as possibly no longer owed. Default: 90 days; an accrual
  carried unsettled from one year end to the next is tested at any age. A shorter age
  flags more accruals.

Ask for the run's materiality in the same pass; without it, materiality is 5% of pre-tax
income for the year. Say that the defaults become days and dollars only once the files are
read, and that the plan shows them for approval before anything runs. When you present
the plan, show the payment cycle measured, the window's days and end date, the threshold
in dollars, the cutoff window and every channel the search reaches or cannot reach.
