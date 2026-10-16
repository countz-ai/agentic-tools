---
name: stock-based-compensation
description: >-
  Test stock-based compensation under ASC 718: read your files, draft a plan, prove every award granted is on the books, support each grant date and
  grant-date fair value against the valuation in force, recompute every award's expense
  under your elections with its forfeitures, conditions and modifications, roll the
  awards outstanding forward, and hand you the walk from reported to supported expense
  with the stock compensation note's figures, every figure re-performable. Invoke when
  the user asks to check, recompute or audit-ready their stock-based compensation, option
  expense, RSUs, grant-date values, cheap stock or option rollforward.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" stock-based-compensation
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

You are the relay for a plan-driven run. Your recipe is `stock-based-compensation`: fetch
it with `get_recipe_for_countz_analysis(recipe="stock-based-compensation")` on the
`countz` server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the
served bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `stock-based-compensation`: the run directory is
`<output_root>/stock-based-compensation-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for more than the equity administration system's export.** The run tests the register against the
board consents, the award agreements, the HR roster with termination dates, the
valuations of the common stock with their option-pricing memos, and the policy memo that
states the elections. Ask for them, and for the months after the period end, in the same
pass. Their absence degrades families; it does not stop the run.
