---
name: income-taxes
description: >-
  Substantiate income taxes under ASC 740 before a first audit: read your files, draft a
  plan, roll the current tax accounts forward against the returns,
  payments and notices, recompute current tax per jurisdiction, measure every temporary
  difference from its book and tax bases, roll operating losses and credits forward
  against the returns with any ownership change limitation, weigh the evidence for the
  valuation allowance, true up each return to its provision, rule each uncertain tax
  position, and hand you the walk from recorded to supported income taxes with the rate
  reconciliation and the disclosure figures, every figure re-performable. Invoke when the
  user asks to review or audit-ready income taxes, the tax provision, deferred taxes, the
  valuation allowance, net operating losses, the research credit, Section 174 research
  costs, a Section 382 limitation, the return-to-provision or uncertain tax positions.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" income-taxes; fi
```

You are the relay for a plan-driven run. Your recipe is `income-taxes`: fetch it
with `get_recipe_for_countz_analysis(recipe="income-taxes")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `income-taxes`: the run directory is
`<output_root>/income-taxes-<company>.<YYYYMMDD-HHMMSS>`.

The accounting standard we use is `run.json.inputs.params.accounting_standard`; follow it where applicable.
