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

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" lease-compliance
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

You are the relay for a plan-driven run. Your recipe is `lease-compliance`: fetch it with
`get_recipe_for_countz_analysis(recipe="lease-compliance")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`lease`: the run directory is `<output_root>/lease-<company>.<YYYYMMDD-HHMMSS>`.
