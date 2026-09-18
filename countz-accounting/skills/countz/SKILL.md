---
name: countz
description: >-
  List the accounting analyses this plugin runs, one line each, and how to start one.
  Invoke when the user asks what countz-accounting can do, which analysis fits their
  question, or how to begin.
context: inline
---

# What countz-accounting runs

Show the table below, then ask which one the user wants and what files they have. Read
no file first.

| ask for | what it does |
|---|---|
| `cash` | Prove out recorded cash and cash equivalents ahead of an audit: an account-by-account plan, transaction-level procedures, the exceptions and open items handed to you. |
| `qoe` | Build a quality-of-earnings EBITDA bridge: validate the figures, rule the cost lines, find every plausible addback, answer management's adjustments, walk EBIT to pro-forma EBITDA. |
| `revenue-recognition` | Test revenue under ASC 606: tie revenue to billing and contracts, place every item in the period its obligation was satisfied, test cutoff, trace deferred and unbilled balances. |
| `revenue-leak` | Find where invoices fail to turn into cash: roll the receivable forward, measure DSO against what the terms allow, test each cause of delay, price every leak in days and dollars. |
| `lease` | Test lease accounting under ASC 842: tie ROU assets, liabilities and lease cost to the books, find leases the register misses, recompute every figure from the contract terms. |
| `tieout` | Establish whether two or more records of the same quantity agree — a general ledger to a trial balance, a sub-ledger to its control account — and analyze what does not. |
| `recon` | Explain the difference between two related records — GL cash to a bank statement, payables to a supplier statement — item by item, every reconciling item evidenced. |
| `countz-analysis` | Run an analysis you describe in your own words: matched to the server's catalog when one fits, otherwise a recipe is authored from your ask and your data before the plan is drafted. |

Then call `get_countz_config` on the `countz` server, once. It returns `catalog_yaml`,
one entry per analysis with `name`, `skill` and `description`. For every entry whose
`skill` is not already an `ask for` above, add a row: `ask for` is *"use countz to do
analysis: <name>"*, `what it does` is the entry's `description` in one line. If the call
is not available or fails, show the table as it is and add one line: "Server catalog not
reachable — showing the built-in analyses."

Every plan-driven run drafts its plan from your files first and runs nothing until you
confirm it.
