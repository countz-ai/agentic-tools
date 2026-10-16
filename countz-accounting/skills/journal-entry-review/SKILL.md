---
name: journal-entry-review
description: >-
  Review the period's journal entries and transactions for error and management
  override, from the company's own ledger: draft a plan, prove the
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

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=$(for d in "${CLAUDE_PLUGIN_ROOT}" "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && echo "${d%/}" && break; done); echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" journal-entry-review
```

`PLUGIN_ROOT=` names this plugin's folder: wherever these documents write
`${CLAUDE_PLUGIN_ROOT}`, use that path. Never search the filesystem for it. If the line
names no path, run `find "$HOME/.claude" -maxdepth 7 -path '*/countz-accounting/scripts/section.py'`
once. Act on the sign-in result as § Sign in first says. Then ask what to run as
§ Ask what to run says: its recipe is the bundled copy the last line names, or, on
`NONE`, the one the server serves. Once the user has answered, read
`<PLUGIN_ROOT>/reference/RUN_CONTRACT.md` whole and the rest of the relay procedure
(`section.py PLAYBOOK_RECIPES.md "Running a recipe"`), and go on from its § 2.

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
