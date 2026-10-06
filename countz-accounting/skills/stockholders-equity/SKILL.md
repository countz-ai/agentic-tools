---
name: stockholders-equity
description: >-
  Substantiate stockholders' equity and the instruments the company issued to raise
  capital: read your files, draft a plan for your confirmation, tie the capitalization
  table to the stock ledger, the approvals and the charter, trace every SAFE, note,
  warrant and preferred series to its agreement, classify each as a liability, temporary
  equity or permanent equity, re-perform each financing, conversion and remeasurement,
  and hand you the walk from reported to supported equity with the fully diluted
  capitalization, every figure re-performable. Invoke when the user asks to check,
  reconcile or audit-ready their cap table, equity, SAFEs, convertible notes, warrants
  or preferred stock, or asks whether an instrument is a liability or equity.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `stockholders-equity`:
fetch it with `get_recipe_for_countz_analysis(recipe="stockholders-equity")`
on the `countz` server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin
the served bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `stockholders-equity`: the run directory is
`<output_root>/stockholders-equity-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the legal record with the books.** The run supports share counts with the stock
ledger, the charter and every amendment, the board and stockholder consents, and the
signed SAFEs, notes, warrants, purchase agreements and side letters. Ask for them, and
for the valuation reports and the months after the period end, in the same pass. Their
absence degrades families; it does not stop the run.
