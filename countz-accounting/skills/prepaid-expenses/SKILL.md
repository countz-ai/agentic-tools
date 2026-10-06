---
name: prepaid-expenses
description: >-
  Substantiate prepaid expenses, deposits and other receivables before a first audit:
  read your files, draft a plan for your confirmation, roll every item forward from
  opening through additions and amortization to closing, trace each addition to its
  invoice or contract and service period, recompute the amortization, find expense
  booked outside the period it covers, test deposits and other receivables against
  receipts after the period end, and hand you the walk from recorded to supported
  balances, every figure re-performable. Invoke when the user asks to review or
  audit-ready prepaid expenses, a prepaid schedule or amortization, security deposits,
  other current or noncurrent assets, or other receivables such as employee advances.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `prepaid-expenses`: fetch it
with `get_recipe_for_countz_analysis(recipe="prepaid-expenses")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `prepaid-expenses`: the run directory is
`<output_root>/prepaid-expenses-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the documents behind the balances.** The run reads the prepaid schedule and
the listings of deposits and other receivables at each period end and the prior one, the
invoices, insurance policies, order forms and contracts behind each item, the leases that
hold a deposit, employee advance agreements, the payroll register, the payables invoice
register and payment register for the year, and the bank statements and invoices for the
months after the period end. Ask for them in the same pass. Their absence degrades
families; it does not stop the run.

**Collect `expense_search_threshold`.** Ask in plain words, with what it controls, its
default and what changing it does. Use this sentence or your own equivalent:

- **Expense search threshold**: invoices and payments in the expense accounts at or above
  this amount, over the year before the period end, are each read for a service period
  that runs past the period end (example: an annual subscription expensed when paid); a
  random selection of smaller ones is read too. Default: your prepaid policy's threshold,
  or performance materiality divided by 2.3 where the policy states none. A lower amount
  reads more invoices and takes longer; a higher one leaves more dollars unread.

Ask for the run's materiality and performance materiality in the same pass. Say that each
default becomes dollars only once the files are read, and that the plan shows both for
approval before anything runs.
When you present the plan, show the prepaid policy as the files state it, the threshold in
dollars, and the months after the period end the records cover.
