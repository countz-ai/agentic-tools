---
name: accounts-receivable
description: >-
  Substantiate trade receivables and the allowance for credit losses before a first
  audit: read your files, draft a plan, tie the aging to the ledger,
  apply the cash received after the period end to each open item, vouch the items it does
  not clear to the invoice and the evidence of delivery, test the credits and write-offs
  after the period end, reclassify credit balances, recompute the allowance under ASC 326
  and back-test it against the write-offs that followed, list the confirmations for the
  auditor, and hand you the walk from recorded to supported receivables, every figure
  re-performable. Invoke when the user asks to review or audit-ready accounts receivable,
  the aging, unbilled receivables, the allowance for credit losses or doubtful accounts,
  bad debt, write-offs, customer credit balances, or receivable confirmations.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" accounts-receivable
```

`PLUGIN_ROOT=` names this plugin's folder: wherever these documents write
`${CLAUDE_PLUGIN_ROOT}`, use that path. When the known places miss, the command searches
`~/.claude/plugins`, then the whole filesystem, itself; run no search of your own. If the
line names no path, tell the user in one line that this plugin's files are not installed
in the session, and stop. Act on the sign-in result as § Sign in first says. Then ask what to run as
§ Ask what to run says: its recipe is the bundled copy the last line names, or, on
`NONE`, the one the server serves. Once the user has answered, read
`<PLUGIN_ROOT>/reference/RUN_CONTRACT.md` whole and the rest of the relay procedure
(`section.py PLAYBOOK_RECIPES.md "Running a recipe"`), and go on from its § 2.

You are the relay for a plan-driven run. Your recipe is `accounts-receivable`: fetch it
with `get_recipe_for_countz_analysis(recipe="accounts-receivable")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `accounts-receivable`: the run directory is
`<output_root>/accounts-receivable-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the documents behind the balances.** The run reads the receivables aging at
invoice grain at each period end, the prior one and each month end; the invoice and
credit memo register; the cash receipts with their application and the customer
remittances; the bank statements for the months after the period end; the write-off
register with its approvals; the customer master and the employee master; the order
forms, contracts, proofs of delivery and acceptance notices behind the larger invoices;
dispute and collections correspondence; the allowance workings and the credit and
collections policy; and the ledger for the year, the prior year and the months after it.
Ask for them in the same pass. Their absence degrades families; it does not stop the run.

**Collect `selection_threshold` and `allowance_elections`.** Ask in plain words, with what
each controls, its default and what changing it does. Use these sentences or your own
equivalents:

- **Selection threshold**: open invoices at or above this amount that were not paid after
  the year end are each checked against the invoice and the proof of delivery, and
  customer balances at or above it go on the list of confirmations for the auditor; a
  random selection of smaller ones is checked too. Default: performance materiality
  divided by 2.31. A lower amount checks more items and takes longer; a higher one leaves
  more dollars unchecked.
- **Allowance elections**: whether your allowance assumes that conditions at the year end
  hold for the life of the receivables, and whether it counts cash collected after the
  year end before the statements are issued. Default: what your policy or your allowance
  workings state; where they state neither, we apply neither and show you the effect of
  each.

Ask for the run's materiality, performance materiality and clearly trivial amount in the
same pass. Materiality is the amount below which a finding is reported as advisory.
Default: 5% of the latest year's pre-tax income where the company made a pre-tax profit in
every year presented; otherwise 1% of the latest year's total expenses. Performance
materiality is the amount above which every suspected problem is tested before the run
finishes. Default: 50% of materiality. Clearly trivial is the difference below which an
item is listed without a proposed entry. Default: 5% of materiality. Say that each default
becomes dollars only once the files are read, and that the plan shows them for approval
before anything runs.
When you present the plan, show the materiality amounts, the selection threshold in
dollars, the allowance policy and elections as the files state them, and the date the
records end.
