---
name: arr-analysis
description: >-
  Analyze the company's recurring revenue from its own billing, contract, customer and
  ledger records: build a cleansed customer cube at customer, product and month grain,
  compute ARR independently on a stated definition and trend it by product, segment,
  channel, region, contract term and every other dimension the data carries, measure
  gross and net retention, renewal, new, expansion, contraction and churn, present
  acquired revenue pro forma and separate organic from acquired growth, name the
  one-time events that break comparability, re-perform management's KPIs with every
  difference attributed, and reconcile ARR to GAAP revenue — every figure re-performable
  from the cube. Invoke when the user asks for an ARR or recurring-revenue analysis, a
  quality of revenue review, net or gross retention, churn, a customer cube, an ARR
  bridge, or ARR reconciled to GAAP revenue.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" arr-analysis; fi
```

You are the relay for a plan-driven run. Your recipe is `arr-analysis`: fetch it with
`get_recipe_for_countz_analysis(recipe="arr-analysis")` on the `countz` server, per
`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served bytes with
`--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `arr-analysis`: the run directory is
`<output_root>/arr-analysis-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
