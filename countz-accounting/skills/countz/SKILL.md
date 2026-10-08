---
name: countz
description: >-
  List the accounting analyses this plugin runs and how to start one, or start one:
  `/countz cash` followed by the ask hands it to that analysis, and an ask in the user's
  own words runs the analysis it describes, matched to the server's catalog or authored
  from the ask. Invoke when the user asks what countz-accounting can do, which analysis
  fits their question, how to begin, says "use countz to do analysis: ..." followed by
  what they want analyzed, or asks for an analysis no named skill covers.
argument-hint: "[analysis] [what you want analyzed]"
context: inline
---

What the user typed after `/countz` decides what you do. Invoked without the slash
command, take the ask from the message that invoked you.

- **Nothing** → § What countz-accounting runs.
- **The first word is an `ask for` in that table** → invoke that skill with the Skill
  tool (`countz-accounting:<ask for>`), the rest of the text verbatim as its arguments.
  That skill takes the rest as the ask and runs the analysis; you do nothing more.
- **Anything else** is the ask → § Run the analysis the ask describes.

## What countz-accounting runs

Show the table below, then ask which one the user wants and what files they have. Read
no file first.

| ask for | what it does |
|---|---|
| `cash` | Prove out recorded cash and cash equivalents ahead of an audit: an account-by-account plan, transaction-level procedures, the exceptions and open items handed to you. |
| `qoe` | Build a quality-of-earnings EBITDA bridge: validate the figures, rule the cost lines, find every plausible addback, answer management's adjustments, walk EBIT to pro-forma EBITDA. |
| `revenue-recognition` | Test revenue under ASC 606: tie revenue to billing and contracts, place every item in the period its obligation was satisfied, test cutoff, trace deferred and unbilled balances. |
| `revenue-leak` | Find where invoices fail to turn into cash: roll the receivable forward, measure DSO against what the terms allow, test each cause of delay, price every leak in days and dollars. |
| `lease` | Test lease accounting under ASC 842: tie ROU assets, liabilities and lease cost to the books, find leases the register misses, recompute every figure from the contract terms. |
| `arr-analysis` | Analyze recurring revenue: build a cleansed customer cube, compute ARR on a stated definition and trend it by every dimension the data carries, measure retention, renewal and churn, split organic from acquired growth, re-perform management's KPIs, reconcile ARR to GAAP revenue. |
| `journal-entry-review` | Review journal entries and transactions for error and override: prove the population complete against the trial balance, screen every entry against fixed criteria, test every selected entry against its support, propose the correcting entries. |
| `stockholders-equity` | Substantiate equity and the capital instruments: tie the cap table to the stock ledger, approvals and charter, classify every SAFE, note, warrant and preferred series as a liability, temporary equity or permanent equity, re-perform each financing and conversion. |
| `stock-based-compensation` | Test stock-based compensation under ASC 718: prove the award population, support each grant date and fair value, recompute every award's expense, roll the awards forward, compute the note's figures. |
| `unrecorded-liabilities` | Search for unrecorded liabilities and test accruals: trace payments and invoices after the period end back to when each was incurred, test cutoff, re-perform each accrual and trace its reversal, walk recorded to supported liabilities. |
| `opening-balances` | Clear opening balances before a first audit: tie each opening trial balance to the prior period's reported closing balances and across any system change, rule every adjustment between a close and the next opening, roll the accumulated deficit forward. |
| `prepaid-expenses` | Substantiate prepaid expenses, deposits and other receivables: roll every item forward, trace each addition to its invoice and service period, recompute the amortization, find expense booked outside its period, walk recorded to supported balances. |
| `fixed-assets` | Substantiate property and equipment and capitalized software: roll every asset class forward, trace each addition to its invoice and in-service date, recompute depreciation and amortization, test the capitalization policy and capitalized labor, walk recorded to supported balances. |
| `contract-costs` | Test capitalized commissions and contract costs under ASC 340-40: rule each commission paid incremental or not, test the practical expedient, support the amortization period, recompute the amortization and the impairment test, walk recorded to supported balances. |
| `debt` | Substantiate borrowings and covenant compliance: roll principal forward against the agreements and lender statements, recompute interest and the effective interest amortization, classify current and noncurrent, compute each covenant as its agreement defines it, walk recorded to supported debt. |
| `income-taxes` | Substantiate income taxes under ASC 740: compute current tax per jurisdiction, schedule every temporary difference, roll losses and credits forward against the returns, support the valuation allowance, reconcile the statutory rate to the effective rate, walk recorded to supported tax balances. |
| `payroll` | Reconcile payroll: tie the register to the ledger per pay period and component, agree it to the payroll tax filings, W-2 totals and bank remittances, test the roster against the people paid, walk recorded to supported payroll cost. |
| `accounts-receivable` | Substantiate trade receivables and the allowance for credit losses: tie the aging to the ledger, prove each balance through invoices, delivery and cash received after the period end, recompute and back-test the allowance, walk recorded to supported receivables. |
| `related-parties` | Identify related parties and their transactions: build the list from the stock ledger, minutes, questionnaires and affiliates' records, match the vendor, customer and employee masters against it, find every related-party transaction and balance in the books, agree each to its agreement, walk the reported related-party figures to the supported ones. |
| `going-concern` | Prepare the going concern figures: schedule obligations due in the year after issuance, re-perform the forecast without unimplemented plans, test it against past results and each plan against its evidence, walk the forecast to liquidity headroom as corrected, state the conditions and the disclosure figures. |
| `create-arr-policy` | Settle how your company computes ARR: read your existing ARR rules from your documents, ask only what they leave open, and save the approved policy that every ARR analysis then runs under. |
| `tieout` | Establish whether two or more records of the same quantity agree — a general ledger to a trial balance, a sub-ledger to its control account — and analyze what does not. |
| `recon` | Explain the difference between two related records — GL cash to a bank statement, payables to a supplier statement — item by item, every reconciling item evidenced. |

Then call `get_countz_config` on the `countz` server, once. It returns `catalog_yaml`,
one entry per analysis with `name`, `skill` and `description`. For every entry whose
`skill` is not already an `ask for` above, add a row: `ask for` is the entry's `name`,
`what it does` is the entry's `description` in one line. If the call
is not available or fails, show the table as it is and add one line: "Server catalog not
reachable — showing the built-in analyses."

Close with how to start one: `/countz <ask for> <what you want>`, or `/countz` followed
by the analysis described in your own words. Every plan-driven run drafts its plan from
your files first and runs nothing until you confirm it.

## Run the analysis the ask describes

Sign in first (`${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md § Sign in first`):
`get_countz_config` returns `catalog_yaml`, one entry per analysis with `name`, `skill`,
`description` and `aliases`. Never carry a list of analyses of your own: the catalog is
fetched on every run, so what the server added since the plugin was installed is there.

**Match the ask against the catalog.** Read each entry's `description` and `aliases`.
The ask matches an entry when it names that analysis — by name, by an alias, or by
describing the entry's stated objective. **An alias hit is a match.** The ask does not
match when it names a different analysis or a different accounting standard (IFRS 16 is
not the ASC 842 entry). A related analysis the catalog does not carry is a miss, never a
near-match: a false match runs the wrong analysis, a miss authors the right one. Say
which entry matched and why in one line, or that none did. Then:

- **A match whose `skill` is an `ask for` in the table**: invoke that skill with the
  Skill tool, the ask verbatim as its arguments. You do nothing more.
- **A single check kind on its own** — a bank reconciliation, a trial-balance tie —
  matches no entry: invoke `recon` (the difference between two related records) or
  `tieout` (whether records of the same quantity agree) the same way.
- **A match with no local skill, or a miss**: you run it, as below.

### Relay a catalog match or a miss

Read `${CLAUDE_PLUGIN_ROOT}/reference/RUN_CONTRACT.md`, and the relay procedure with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "Running a recipe"`.

You are the relay for a plan-driven run whose recipe is not fixed in advance. You do no
analysis and you open no client file. Your `--skill` is `countz`: the run directory is
`<output_root>/countz-<company>.<YYYYMMDD-HHMMSS>`.

The relay procedure's § 1 collects the ask in the user's words as `instructions`. What
differs from a named shim is `PLAYBOOK_RECIPES.md § Fetch the recipe and register`,
which for this skill runs as:

1. **On a match**, run `scripts/bundled_recipe.py <the entry's name>` first and pin the
   bundled copy when it prints one (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`).
   Otherwise call `get_recipe_for_countz_analysis(recipe=<the entry's name>)` and
   continue as a named shim does: write `recipe_markdown` to a file and register with
   `--recipe <that file> --recipe-version <recipe_version>`
   (`PLAYBOOK_RECIPES.md § Fetch the recipe and register`).
2. **On a miss**, scrub the ask before anything crosses, under
   `${CLAUDE_PLUGIN_ROOT}/reference/SCRUB.md` (read it whole). Register the run first
   (the registration in `PLAYBOOK_RECIPES.md § Fetch the recipe and register`, without
   `--recipe`). Then two separate invocations of the `countz-accounting:scrubber` agent
   (the Agent tool, `subagent_type: countz-accounting:scrubber`, a fresh agent each time,
   the brief stating the mode) — no script decides what identifies the company:

   1. **Scrub.** Dispatch the scrubber with `mode: scrub`, the ask verbatim (from
      `instructions`), and the registration from `run.json`: `inputs.company`, every
      source's `name`, and any entity or alias the user named. It returns `SEND:` (the
      description) and `REMOVED:` (one line per removal, class and replacement).
   2. **Blind check.** Dispatch the scrubber again, as a new invocation, with
      `mode: blind` and **only the `SEND` text** — never the ask, the registration or the
      removal list. It returns `VERDICT: clean` or `VERDICT: flagged` with its flags.
   3. On `flagged`, repeat 1 passing the flags, then 2 on the new text. After three
      rounds without `clean`, send nothing: say so in one line and go to `create-recipe`
      (below) with the full ask, which never leaves the machine.
   4. Record it — the removal lists, the verdicts and the text sent:

      ```
      python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py record-scrub <run_dir> --json @<run_dir>/scrub-draft.json
      ```

      where the file (written with the Write tool, so no quoting touches the text) holds `{"send": "<SEND text>", "rounds": [{"removed": [{"category": "...", "replacement": "..."}], "verdict": "clean|flagged", "flags": [{"category": "...", "where": "..."}]}, ...]}`.
      It refuses unless the last round is `clean`, writes `scrub.json`, deletes the draft,
      and prints `SEND:` — the exact text.

   **Tell, then send.** Put the `SEND` text to the user in one line — *"Nothing in the
   catalog covers this. I'm sending Countz this description and nothing else, so it can
   serve or plan a recipe for it: `<SEND text>`"* — then call
   `get_recipe_for_countz_analysis(ask=<SEND text>)`, naming no recipe, with the bytes
   `record-scrub` printed. The server matches once more against its aliases.
   - `match` is `alias`: continue as step 1, with the body it returned.
   - `match` is `not_found`: dispatch `create-recipe` (below). The full ask stays in
     `run.json.inputs.params.instructions`; only the `SEND` text crossed.

### Authoring the recipe

`create-recipe` is a fork: it reads the registered sources under the bounded-read rules
and cannot ask the user anything, so it runs twice, exactly as `check-plan` runs again
on `revise=`.

1. **Draft stage.** `run_state.py dispatch <run_dir> --step recipe --args '<one-line JSON>'`
   with `ask=` (the user's ask verbatim, from `instructions`), `catalog=` (the
   `catalog_yaml` you fetched), then the plain Skill call. It returns the questions it
   needs answered: the objective in one sentence, the population, the source classes it
   found, the grain the data supports, and what the ask leaves open. `record`.
2. **Relay.** Put those questions to the user, in its words, and collect the answers.
3. **Author stage.** Dispatch `create-recipe` again on a new seq with the same arguments
   plus `answers=` (the user's answers, verbatim). It writes
   `<run_dir>/recipes/<name>.md`, runs `scripts/validate_recipe.py` over it, and ends
   `blocked` rather than hand the plan a malformed recipe. `record`, then pin the file:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID} \
       --sources '[]' --recipe <run_dir>/recipes/<name>.md
   ```

   Show the recipe to the user (`preview.py` names it) before the plan step. A generated
   recipe belongs to this run: a later run over the same analysis generates again.

Where the pinned recipe declares `arr_policy`, served or generated, settle it first
(`PLAYBOOK_RECIPES.md § Fetch the recipe and register`, *The ARR policy*). Then
`PLAYBOOK_RECIPES.md § Plan`, with `recipe=` the pinned path and `instructions=` the
ask, and everything after it unchanged.
