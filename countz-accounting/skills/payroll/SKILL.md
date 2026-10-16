---
name: payroll
description: >-
  Reconcile payroll before a first audit: read your files, draft a plan, tie the payroll register to the ledger per pay run, component and
  income statement line, prove gross to net, agree the register to the federal and state
  payroll tax returns and the W-2 totals, recompute employer taxes, trace every
  remittance to the bank and the agencies' records, agree provider or PEO invoices to the
  ledger, test the people paid against the roster and contractor payments against the
  1099 totals, and hand you the walk from recorded to supported payroll cost, every
  figure re-performable. Invoke when the user asks to review, reconcile or audit-ready
  payroll, payroll taxes, Forms 941 or 940, W-2s, state payroll filings, a PEO, ghost
  employees, or contractor 1099s.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=$(for d in "${CLAUDE_PLUGIN_ROOT}" "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && echo "${d%/}" && break; done); echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" payroll
```

`PLUGIN_ROOT=` names this plugin's folder: wherever these documents write
`${CLAUDE_PLUGIN_ROOT}`, use that path. Never search the filesystem for it. If the line
names no path, run `find "$HOME/.claude" -maxdepth 7 -path '*/countz-accounting/scripts/section.py'`
once. Act on the sign-in result as § Sign in first says. Then ask what to run as
§ Ask what to run says: its recipe is the bundled copy the last line names, or, on
`NONE`, the one the server serves. Once the user has answered, read
`<PLUGIN_ROOT>/reference/RUN_CONTRACT.md` whole and the rest of the relay procedure
(`section.py PLAYBOOK_RECIPES.md "Running a recipe"`), and go on from its § 2.

You are the relay for a plan-driven run. Your recipe is `payroll`: fetch it
with `get_recipe_for_countz_analysis(recipe="payroll")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `payroll`: the run directory is
`<output_root>/payroll-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the payroll provider's and the agencies' records with the books.** The run
reads the payroll register at employee and pay-run grain for the year and the months
after it, the provider's tax and deposit reports, the federal and state payroll tax
returns as filed (Forms 941 and 940 with their schedules, state withholding and
unemployment wage reports, W-2s and W-3, 1099s), the agencies' payment records and rate
notices, the PEO or provider agreement and invoices, the HR roster with hire,
termination and department history, offer letters and pay-rate approvals, time records
for hourly staff, the equity administrator's exercise and settlement records, the bank
statements, the payables register, and the trial balance and ledger detail. Ask for them
in the same pass. Their absence degrades families; it does not stop the run.

**Collect `headline_scope`.** Ask in plain words, with its default and what changing it
does. Use this sentence or your own equivalent:

- **What the headline payroll cost holds**: by default, employee payroll cost only
  (wages, employer taxes, benefits and reimbursements); payments to contractors are
  reconciled to the 1099s and shown on their own line beside it. Say so if you want
  contractor cost added to the headline instead.

Ask for the run's materiality, performance materiality, clearly trivial amount and
investigation threshold in the same pass, in plain words:

- **Materiality**: the amount below which a finding is reported as advisory. Default: 5%
  of the latest year's pre-tax income where the company made a pre-tax profit in every
  year presented; otherwise 1% of the latest year's total expenses.
- **Performance materiality**: the amount above which every suspected problem is tested
  before the run finishes. Default: 50% of materiality.
- **Clearly trivial**: a difference between two records at or below this amount is
  listed and proposed as no correction. Default: 5% of materiality.
- **Investigation threshold**: a month whose payroll cost on a line departs from what
  headcount and pay rates predict by more than this amount is investigated. Default: 50%
  of performance materiality. You may set another amount.

Say that each default becomes dollars only once the files are read, and that the plan
shows them for approval before anything runs. When you present the plan, show the four
amounts in dollars, the headline scope, who files the company's payroll returns (the
company, a provider or a PEO), the pay calendar, the returns and states it registers, and
the date the records end.
