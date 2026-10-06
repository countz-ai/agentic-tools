---
name: income-taxes
description: >-
  Substantiate income taxes under ASC 740 before a first audit: read your files, draft a
  plan for your confirmation, roll the current tax accounts forward against the returns,
  payments and notices, recompute current tax per jurisdiction, measure every temporary
  difference from its book and tax bases, roll operating losses and credits forward
  against the returns with any ownership change limitation, weigh the evidence for the
  valuation allowance, true up each return to its provision, rule each uncertain tax
  position, and hand you the walk from recorded to supported income taxes with the rate
  reconciliation and the disclosure figures, every figure re-performable. Invoke when the
  user asks to review or audit-ready income taxes, the tax provision, deferred taxes, the
  valuation allowance, net operating losses, the research credit, Section 174 research
  costs, a Section 382 limitation, the return-to-provision or uncertain tax positions.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `income-taxes`: fetch it
with `get_recipe_for_countz_analysis(recipe="income-taxes")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `income-taxes`: the run directory is
`<output_root>/income-taxes-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the returns and the authorities' records with the books.** The run reads the
federal, state, local and foreign income tax returns for every year in scope and the year
before, with their schedules, amended returns and elections; the tax authorities'
transcripts, notices, assessments and refunds; the bank statements carrying each tax
payment; the provision workpapers, the deferred tax roll-forward and the tax basis balance
sheet; the research credit study and the payroll tax returns that apply the credit; the
research cost schedules; the ownership change study and the stock ledger; the state
apportionment workpapers; the valuation allowance and uncertain tax position memos; the
payroll register by state; and the draft income tax note. Ask for them in the same pass.
Their absence degrades families; it does not stop the run.

**Collect `reporting_entity`.** Ask in plain words, with what it controls, its default and
what changing it does. Use this sentence or your own equivalent:

- **Reporting entity**: whether the statements will be filed with the SEC (a public
  business entity) or not. A public business entity's income tax note shows the tax
  effect of each kind of difference and the rate reconciliation in dollars; a private
  company's shows less. Default: private.

Ask for the run's materiality and performance materiality in the same pass. Materiality is
the amount below which a finding is reported as advisory. Default: 5% of the latest year's
pre-tax income where the company made a pre-tax profit in every year presented; otherwise
1% of the latest year's total expenses. Performance materiality is the amount above which
every suspected problem is tested, and every book-tax difference traced to its records,
before the run finishes. Default: 50% of materiality.
When you present the plan, show the materiality and the performance materiality in
dollars, every jurisdiction it registers with its filing status, the returns the files
carry per jurisdiction and year, the company's elections as the files state them, and the
date the records end.
