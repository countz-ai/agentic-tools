---
name: qoe
description: >-
  Build a quality-of-earnings EBITDA bridge from the company's own records: validate
  the revenue and cost figures it is built on, break the income statement down to ruled
  cost lines, identify every plausible addback from first principles, answer
  management's proposed adjustments, and walk EBIT through reported EBITDA,
  management's adjusted view where one exists, and diligence-adjusted EBITDA to
  pro-forma — argued sell-side unless the user asks for a buy-side engagement, with every
  figure re-performable. Invoke when the user asks for a QoE or quality of earnings, an
  EBITDA bridge, adjusted or normalized EBITDA, or an addback analysis.
context: inline
---

Your first tool call is `get_countz_config` on the `countz` server. Then, whatever it
returned, run this one command, and read nothing else first:

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$COUNTZ_PLUGIN_ROOT" "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; echo "PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" quality-of-earnings
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

You are the relay for a plan-driven run. Your recipe is `quality-of-earnings`: fetch it with
`get_recipe_for_countz_analysis(recipe="quality-of-earnings")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`qoe`: the run directory is `<output_root>/qoe-<company>.<YYYYMMDD-HHMMSS>`.

Put `perspective` to the user with the rest of the collection. Where they do not choose,
use `sell_side`: the audience is the company's own executives. Only the user chooses
`buy_side`; never infer it from the data room (`RUN_CONTRACT.md` § Parameters).
