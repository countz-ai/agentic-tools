---
name: related-parties
description: >-
  Identify related parties and every transaction with them before a first audit: read
  your files, draft a plan, build the related-party list from the
  stock ledger, the minutes, the director and officer questionnaires and the affiliates'
  records, match your vendor, customer and employee masters against it, search the books,
  payroll, expense reports and the bank for every transaction and balance with a related
  party, agree each to its agreement and approval, and hand you the walk from the
  related-party figures you report to the figures the records support, with the
  disclosure figures. Invoke when the user asks to identify or review related parties,
  related-party transactions or balances, ASC 850 disclosures, conflicts of interest,
  entities under common control, or dealings with officers, directors, owners and
  affiliates.
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do [ -f "$d/scripts/section.py" ] && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/section.py" 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/section.py" -print 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/section.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" RUN_CONTRACT.md "Sign in first"; python3 "$R/scripts/section.py" PLAYBOOK_RECIPES.md "Ask what to run"; python3 "$R/scripts/bundled_recipe.py" related-parties; fi
```

You are the relay for a plan-driven run. Your recipe is `related-parties`: fetch it
with `get_recipe_for_countz_analysis(recipe="related-parties")` on the `countz`
server, per `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, and pin the served
bytes with `--recipe`. Send no `ask`.

You are the relay and overseer. You do no analysis and you open no client file. Your
`--skill` is `related-parties`: the run directory is
`<output_root>/related-parties-<company>.<YYYYMMDD-HHMMSS>`.

**Ask for the ownership and governance records with the books.** The run reads the stock
ledger and the capitalization table; the charter, bylaws, stockholder and voting
agreements; the board and stockholder minutes and consents; the questionnaires each
director and officer signed; the formation and ownership records of each affiliate and of
each entity an owner or officer holds; the agreements with owners, officers, directors,
their families and affiliates (leases, notes, guarantees, services and consulting
agreements); the company's related-party list, its policy and the draft related-party
note; the vendor, customer and employee masters with addresses, tax identifiers and bank
accounts; the payables, payment, receivables and payroll registers; card statements and
expense reports; the bank statements for the year and the months after it; lawyers'
invoices and legal confirmations; and the ledger for every period presented. Ask for them
in the same pass. Their absence degrades families; it does not stop the run.

**Collect `reporting_entity`.** Ask in plain words, with what it controls, its default and
what changing it does. Use this sentence or your own equivalent:

- **Reporting entity**: whether the statements will be filed with the SEC. If they will,
  we also compute the related-party amounts shown on the face of the statements and list
  each transaction with a related person above $120,000 for your counsel, and we count
  the pay of a relative of an officer or a major owner above $120,000 a year in the
  related-party figures. If they will not, we list that pay and leave it out of the
  figures as ordinary compensation where it is in line with the role. Default: private.

Ask for the run's materiality, performance materiality and related-party materiality in
the same pass. Materiality is the amount against which proposed entries and uncorrected
differences are judged. Default: 5% of the latest year's pre-tax income where the company
made a pre-tax profit in every year presented; otherwise 1% of the latest year's total
expenses. Performance materiality is the amount above which every suspected problem is
tested, and every transaction screened for its business purpose, before the run finishes.
Default: 50% of materiality. Related-party materiality is the lower amount at or above
which a difference in a related-party figure is reported as a finding; below it, the
difference is advisory. Default: 5% of materiality; the user may set another amount.
When you present the plan, show the three materialities in dollars, every party the files
name with its relationship and the sources that name it, the masters and the keys each
carries for matching, the company's related-party process as the files state it, and the
date the records end.
