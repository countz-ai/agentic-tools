---
name: debt
description: >-
  Substantiate borrowings and covenant compliance before a first audit: read your files,
  draft a plan for your confirmation, roll principal forward against the loan agreements
  and the lender statements, recompute interest, accrued interest and the effective
  interest amortization of discounts, issuance costs and end-of-term fees, rule each
  amendment, classify each borrowing current or noncurrent with every breach and waiver,
  compute each covenant the way the agreement defines it, schedule the maturities, and
  hand you the walk from recorded to supported debt, every figure re-performable. Invoke
  when the user asks to review or audit-ready debt, borrowings, a term loan, venture
  debt, a revolving line or notes payable, interest expense or accrued interest on a
  loan, debt issuance costs or an end-of-term fee, debt classification, a loan
  amendment, or covenant compliance.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `debt`: fetch it
with `get_recipe_for_countz_analysis(recipe="debt")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `debt`: the run directory is
`<output_root>/debt-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the lenders' records with the books.** The run reads every loan agreement with
its amendments, waivers, consents and fee letters, the lenders' monthly statements and
invoices, rate notices, notices of default, payoff letters, warrant agreements issued to a
lender, intercreditor and control agreements, the debt schedule and its amortization
tables, the compliance certificates as delivered with their workings, the monthly packages
sent to the lenders, the bank statements for the year and the months after the period end,
the receivables aging and deferred revenue where a covenant reads them, and board minutes.
Ask for them in the same pass. Their absence degrades families; it does not stop the run.

**Collect `evaluation_date`.** Ask in plain words, with what it controls, its default and
what changing it does. Use this sentence or your own equivalent:

- **Evaluation date**: the date through which we read waivers, amendments, refinancings
  and covenant tests after year end to decide whether each loan is current or noncurrent.
  Default: the last date your records cover. If you know when the statements will be
  issued, give that date; a waiver signed after it does not count.

Ask for the run's materiality and performance materiality in the same pass. Materiality is
the amount below which a finding is reported as advisory. Default: 5% of the latest year's
pre-tax income where the company made a pre-tax profit in every year presented; otherwise
1% of the latest year's total expenses. Performance materiality is the amount above which
every suspected problem is tested before the run finishes. Default: 50% of materiality.
When you present the plan, show the materiality and the performance materiality in
dollars, every borrowing and covenant it registers, each covenant's test dates, the
evaluation date and the date the records end.
