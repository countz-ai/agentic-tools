---
name: revenue-leak
description: >-
  Find where invoices fail to turn into cash, from the company's own records, the
  collections record layered on where it exists: draft a plan, tie the aging to the books, roll the receivable forward, measure DSO
  against the best-possible DSO the terms set, test each candidate cause of delay as a
  claim the data can refute, trace cash application, give every open item its behavior
  group and, where recorded, its cause, owner and next action, and hand the reader the
  billed-to-collected bridge and the DSO bridge to the supported target, every leak
  priced in days and dollars, every refuted cause reported, every figure re-performable.
  Invoke when the user asks for a DSO or days sales outstanding diagnostic, a
  receivables or collections review, an aging or past-due analysis, where the cash in
  receivables is, why invoices are not being paid, how to improve collections, what is
  leaking between billing and cash, or to test collection hypotheses against their data.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" revenue-leak; fi
```

You are the relay for a plan-driven run. Your recipe is `revenue-leak`: fetch it with
`get_recipe_for_countz_analysis(recipe="revenue-leak")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file; Your `--skill` is
`revenue-leak`: the run directory is
`<output_root>/revenue-leak-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
