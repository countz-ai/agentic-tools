---
name: revenue-leak
description: >-
  Find where invoices fail to turn into cash, from the company's own records, the
  collections record layered on where it exists: draft a plan for your
  confirmation, tie the aging to the books, roll the receivable forward, measure DSO
  against the best-possible DSO the terms set, test each candidate cause of delay as a
  claim the data can refute, trace cash application, give every open item its behaviour
  group and, where recorded, its cause, owner and next action, and hand the reader the
  billed-to-collected bridge and the DSO bridge to the supported target, every leak
  priced in days and dollars, every refuted cause reported, every figure re-performable.
  Invoke when the user asks for a DSO or days sales outstanding diagnostic, a
  receivables or collections review, an aging or past-due analysis, where the cash in
  receivables is, why invoices are not being paid, how to improve collections, what is
  leaking between billing and cash, or to test collection hypotheses against their data.
context: inline
---

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run. Your recipe is `revenue-leak`: fetch it with
`get_recipe_for_countz_analysis(recipe="revenue-leak")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`revenue-leak`: the run directory is
`<output_root>/revenue-leak-<company>.<YYYYMMDD-HHMMSS>`.

Four things this recipe needs from you that a plain relay pass would miss:

**Put `leak_stance` to the user.** Where they do not choose, take `operating`: the reader
is the collections owner and the finance executives above them, and the report ends in
what to do. `diligence` is the user's to declare; do not read it off the data room
(`RUN_CONTRACT.md` § Parameters).

**Ask for more than the review period.** The recipe's § The period set requires at least
one full prior period of billing files, because receipts in the review period settle
invoices issued before it. Say so when collecting, so the user gathers it in one pass rather than
two.

**Ask for the collections record as a source.** Anything stating why items are late, who
owns the next action and what was promised — an activity log, a dispute log, promises to
pay, an escalation list, the collections policy with its ladder. Say what it adds: a
cause the record states stands as documented, where a cause drawn from behaviour alone
stands as indicative with the question that would settle it. Its absence changes no
check; do not press for it.

**Do not let the plan flatten R3's sequencing.** R3 settles what population the files
describe, and R4 through R8 each assert that scope in their own records. If the drafted
plan puts R3 in the same wave as its dependents, send it back: the checks would ship
asserting a scope their sibling was concurrently disproving, and the defect is invisible
in the check records themselves — only the plan can prevent it.
