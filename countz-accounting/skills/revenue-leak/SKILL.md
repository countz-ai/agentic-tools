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

Four things this recipe needs from you that a plain relay pass would miss:

**Ask for more than the review period.** The recipe's § The period set requires at least
one full prior period of billing files, because receipts in the review period settle
invoices issued before it. Say so when collecting, so the user gathers it in one pass rather than
two.

**Ask for the collections record as a source.** Anything stating why items are late, who
owns the next action and what was promised — an activity log, a dispute log, promises to
pay, an escalation list, the collections policy with its ladder. Say what it adds: a
cause the record states stands as documented, where a cause drawn from behavior alone
stands as indicative with the question that would settle it. Its absence changes no
check; do not press for it.

**Do not let the plan flatten R3's sequencing.** R3 settles what population the files
describe, and every family from R4 on reads it (`params.scope_from`). If the drafted
plan runs R3 in the same wave as a dependent, send it back: that check would ship
asserting a scope its sibling was concurrently disproving, and the defect is invisible
in the check records themselves — only the plan can prevent it.

**Put the lines of inquiry in front of the user.** When you present the plan, show the
R6 lines of inquiry the planner chose, the leak bucket each tests, the patterns it
skipped with its reason, any list values it added, and each bucket no line or family
measures with its `D.`. Send back a plan with a bucket that has neither a line nor a
`D.`.
