---
name: fixed-assets
description: >-
  Substantiate property and equipment and capitalized software before a first audit:
  read your files, draft a plan, roll every asset class forward,
  trace each addition to its invoice and placed-in-service date, rule each disposal,
  recompute depreciation and amortization from your policy's lives and methods, test
  the capitalization policy both ways, trace capitalized software labor to payroll and
  project records, and hand you the walk from recorded to supported balances, every
  figure re-performable. Invoke when the user asks to review or audit-ready fixed
  assets, property and equipment, the fixed asset register or depreciation, leasehold
  improvements, construction in progress, intangible assets, the capitalization policy,
  or capitalized internal-use or hosting implementation software costs.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" fixed-assets; fi
```

You are the relay for a plan-driven run. Your recipe is `fixed-assets`: fetch it
with `get_recipe_for_countz_analysis(recipe="fixed-assets")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `fixed-assets`: the run directory is
`<output_root>/fixed-assets-<company>.<YYYYMMDD-HHMMSS>`.
