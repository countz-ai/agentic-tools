---
name: extract-arr-policy
description: >-
  Read the company's own ARR rules out of the registered documents: find every policy
  memo, KPI definition, filing, board or lender pack and management ARR file that states
  how ARR is computed, and write each stated rule as a decision of the ARR policy with
  its quote and citation, for create-arr-policy to resolve.
context: fork
agent: countz-accounting:planner
background: false
user-invocable: false
---

# Read the company's ARR rules

Arguments: `run_dir`, `seq`, `out` (the stated-rules file to write, under
`<run_dir>/arr_policy/`), `company`, and optionally `paths` (the registered sources to
read; absent, every registered source). You read client files and you decide nothing:
you record what the documents state, in the policy's vocabulary, and `create-arr-policy`
settles the rest with the user.

Start with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/step_record.py start <run_dir> <seq>`.
Read `${CLAUDE_PLUGIN_ROOT}/reference/CONDUCT.md` § Reading client files and
`${CLAUDE_PLUGIN_ROOT}/reference/ARR_POLICY.md` except § Computing ARR
(`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/ARR_POLICY.md "The model" "The file" "Instructions" "Where a policy lives" "How a run carries it" "Applying the policy"`),
then print the catalog:
`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/arr_policy.py catalog`. Every value you write is
an option id the catalog prints.

## 1. Find the documents that state ARR rules

Peek every registered source through `scripts/peek.py`, a folder in one call. A document
states ARR rules when it says, in words, how recurring revenue or its measures are
computed:

- an ARR, recurring-revenue or revenue-recognition policy memo;
- a KPI or metrics definition page, or a definitions or notes tab in a management ARR,
  MRR, bookings or retention file;
- a filing's key business metrics section, or a board, investor or lender pack that
  defines ARR, net retention or churn;
- a credit agreement's definition of recurring revenue.

A file that only carries figures states no rule. How management's numbers behave is a
question the run's own checks answer, so never infer a rule from figures. Read each
stating document at the depth its definition needs: the page, the section or the tab,
through a targeted read, never the whole file into your context.

## 2. Map each statement to the policy

For each sentence that states a rule, write the decision it settles:

- **A decision.** Under `decisions`, keyed by id: `{value, basis: stated, quote, cite}`.
  `quote` is the sentence verbatim. `cite` names the file and the page, section, sheet
  or cell. A composite decision takes only the fields the sentence settles.
- **A position or a convention the document names directly.** For example "ARR is
  contracted value" settles `source`, and "retention is measured on trailing twelve
  months revenue" settles `retention.basis`. Write it under `policies.<name>` as
  `{position, set_by: stated, cite}` or under `conventions.<name>` as
  `{value, set_by: stated, cite}`.
- **A rule that fits no option.** Most rules specific to the business are like this: how
  its own products, plans or channels are counted. Write it under `instructions` as
  `{text, applies_to, source: stated, cite, quote}`: `text` restates the rule in words a
  worker applies to rows, and `applies_to` names the decisions it refines. Never bend a
  rule into the nearest option. A rule that contradicts the value a decision it states
  takes goes into `notes` as `"<quote> (<cite>)"`, for the user to rule on.

Two documents that state the same decision differently are both written into `notes`
with their citations, and the decision is left out. A conflict is the user's to settle.

Write `out` as the stated input `ARR_POLICY.md` § The file describes: `company`,
`documents` (each document read, `{path, title}`), `policies`, `conventions`,
`decisions`, `instructions`, `notes`. Then run
`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/arr_policy.py resolve <out>`. An `ERROR` line is
yours to fix in the file before you finish: a value that is not an option id, or a
decision id that does not exist. The `ASK` and `STATUS` lines are for the user and need
nothing from you.

## 3. Finish

Write `<run_dir>/arr_policy/finish.json` holding `conclusion` (two sentences: which
documents state the company's ARR rules, and how many decisions they settle),
`produced` (`[out]`, relative to `run_dir`), `consumed` (`{path: used_for}` for each
document you opened), and `notes` (the count of conflicts). Where no document
states a rule, the outcome is still `complete`: say so in `conclusion`, and write `out`
with `company`, `documents: []` and no decisions. Then:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/step_record.py finish <run_dir> <seq> --json <run_dir>/arr_policy/finish.json
```

## Return

At most five lines: `out`; the documents that state rules; the number of decisions,
positions, conventions and instructions stated; the number of conflicts left in `notes`.
