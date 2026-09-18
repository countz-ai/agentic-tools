---
name: lease
description: >-
  Test whether the company's leases are accounted for under ASC 842 as their contracts
  support, from its own records: tie the right-of-use assets, lease liabilities and
  lease cost to the books, sweep the spend and the contracts for leases the register
  misses, trace every lease's terms to its agreement, recompute every liability, asset
  and period cost from those terms at the recorded rate, re-apply the classification,
  term, rate and modification judgments to the contracts that carry the balances and
  the risk, compute the figures the lease note requires, and hand the reader the
  reported lease liability, right-of-use asset and lease cost walked to the figures as
  supported — every adjustment an entry with its counter-account, every figure
  re-performable. Invoke when the user asks to check, test or audit-ready lease
  accounting or ASC 842 compliance, right-of-use assets or lease liabilities, embedded
  or unrecorded leases, lease classification, or the lease disclosures.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `lease-compliance`: fetch it with
`get_recipe_for_countz_analysis(recipe="lease-compliance")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`lease`: the run directory is `<output_root>/lease-<company>.<YYYYMMDD-HHMMSS>`.
