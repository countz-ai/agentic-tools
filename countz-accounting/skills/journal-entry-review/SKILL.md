---
name: journal-entry-review
description: >-
  Review the period's journal entries and transactions for error and management
  override, from the company's own ledger: draft a plan for your confirmation, prove the
  entry population complete against the trial balance for every entity, screen every
  entry against criteria fixed before the results, test every selected entry against its
  support, and hand you the misstated and unsupported entries, the proposed correcting
  entries with their effect on pre-tax income, the patterns across entries and the
  holding balances to clear, every figure re-performable. Invoke when the user asks to
  review, test or scrub journal entries or transactions, test for management override,
  test 100% of the transactions in an account, find miscoded, uncategorized, duplicate or
  unusual entries, or clean up books someone else kept.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `journal-entry-review`: fetch it
with `get_recipe_for_countz_analysis(recipe="journal-entry-review")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `journal-entry-review`: the run directory is
`<output_root>/journal-entry-review-<company>.<YYYYMMDD-HHMMSS>`.

Three things this recipe needs from you that a plain relay pass would miss:

**Ask for more than the review period.** The criteria read the twelve months before the
period as the company's baseline, and the months after it for late postings and
reversals (§ The period set). Ask for the user listing with roles and approval limits,
the chart of accounts and the support behind the entries in the same pass. Their absence
degrades criteria; it does not stop the run.

**Collect `full_test_accounts`.** Ask whether any account should have every entry traced
to its document. Default `none`. Naming accounts adds that testing and never narrows the
screen.

**Put the criteria in front of the user.** When you present the plan, show each
criterion with its parameters, the ones degraded with the field they lack, the lines of
inquiry and the Toolbox patterns skipped with their reason. Send back a plan that leaves
an entity or a journal source out of the screen.
