---
name: going-concern
description: >-
  Prepare the figures for the going concern evaluation under ASC 205-40 before a first
  audit: read your files, draft a plan for your confirmation, schedule every obligation due
  in the year after the statements are issued, tie your forecast to the bank, re-perform it
  without the plans not yet implemented and project each covenant on it, measure earlier
  forecasts against actual results, list the conditions and events, test each of your plans
  against its evidence, and hand you the walk from your forecast to liquidity headroom as
  corrected, before and after the plans, with the disclosure figures. The substantial doubt
  conclusion stays with you and your auditor. Invoke when the user asks about going
  concern, substantial doubt, cash runway, burn rate or liquidity before an audit.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `going-concern`: fetch it
with `get_recipe_for_countz_analysis(recipe="going-concern")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `going-concern`: the run directory is
`<output_root>/going-concern-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the forecast and the records behind it.** The run reads the cash flow forecast
with its assumptions, every earlier forecast and budget, the bank statements for the year
and every month after the period end, the trial balances and GL detail, the loan
agreements with their amendments, waivers and lender notices, the leases and contracts with
minimum commitments, the convertible notes, SAFEs, warrant and preferred stock terms, the
payables aging and payment register, the payroll register and payroll tax filings, board
minutes and investor decks, and the documents behind each plan (term sheets, purchase
agreements, commitment or support letters, approvals, reduction-in-force lists). Ask for
them in the same pass. Their absence degrades families; it does not stop the run.

**Collect `issuance_date`.** Ask in plain words, with what it controls, its default and
what changing it does. Use this sentence or your own equivalent:

- **Issuance date**: the date your audited statements are expected to be issued or ready
  to be issued. The run tests your liquidity over the twelve months after it. Default: the
  last date your records cover. A later date moves the end of the twelve months later and
  brings more obligations into it.

Ask for the run's materiality and performance materiality in the same pass. Materiality is
the amount below which a finding is reported as advisory. Default: 5% of the latest year's
pre-tax income where the company made a pre-tax profit in every year presented; otherwise
1% of the latest year's total expenses. Performance materiality is the amount above which
every suspected problem is tested before the run finishes. Default: 50% of materiality.
Say that each default becomes dollars only once the files are read.
When you present the plan, show the materiality and the performance materiality in
dollars, the assessment date and the end of the twelve months after it, the date the
records end, the forecast the run treats as the base case, and every plan it registers.
