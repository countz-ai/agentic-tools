---
name: contract-costs
description: >-
  Test capitalized commissions and other costs to obtain and fulfill customer contracts
  under ASC 340-40 before a first audit: read your files, draft a plan, read the commission plans against the commissions paid, rule each payment
  incremental or not, test the one-year practical expedient, support the amortization
  period against contract terms, renewals and customer life, recompute the amortization
  and the current and noncurrent split, run the impairment test, and hand you the walk
  from recorded to supported balances, every figure re-performable. Invoke when the user
  asks to review or audit-ready capitalized or deferred commissions, contract costs,
  costs to obtain or fulfill a contract, commission amortization, or ASC 340-40.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" contract-costs
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

You are the relay for a plan-driven run. Your recipe is `contract-costs`: fetch it
with `get_recipe_for_countz_analysis(recipe="contract-costs")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `contract-costs`: the run directory is
`<output_root>/contract-costs-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the records behind the costs.** The run reads the commission plans of every role
and year with their effective dates, the commission system's statement lines at deal
grain, the contract register with renewals and terminations, the order forms, the payroll
register by earning code, referral and partner agreements and their invoices, the deferred
commission schedules at each period end and the prior one, the capitalization policy, and
any customer life or retention analysis. Where the company has never capitalized, ask for
the commission records back over the amortization period. Ask for them in the same pass.
Their absence degrades families; it does not stop the run.

Ask for the run's materiality and performance materiality in the same pass. Say that the
defaults become dollars only once the files are read, and that the plan shows them for
approval before anything runs.
When you present the plan, show the capitalization policy as the files state it, the
amortization period per portfolio, and the months after the period end the records cover.
