# The ARR policy

No accounting standard defines annual recurring revenue. Two analysts working from the
same records compute different ARR, because a definition is a bundle of choices: which
record sets the amount, what counts as recurring, when a customer enters and leaves,
and at what price. A run that computes ARR therefore computes it under a written policy
the company approved, and states that policy beside every figure that depends on it.

This document is the contract for that policy. The catalog itself (every purpose,
position, convention, decision, option and derivation) has one home,
`scripts/arr_policy.py`. Print it with:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/arr_policy.py catalog
```

## The model

An ARR policy settles **31 decisions**. It does not answer them one by one. Four
**policies** each take a position on a spectrum from conservative to expansive, and the
position decides the decisions that policy owns:

| policy | the question it answers |
|---|---|
| `source` | Which record do we trust for the amount? |
| `recurrence` | Would this revenue come back next year without a new sale? |
| `lifecycle` | When does a customer's ARR start, and when does it stop? |
| `value` | At what annual price? |

A **purpose** sets all four positions at once: `operator`, `public_reporting`,
`sell_side` or `buy_side`. It is the first question to ask, because one answer settles
18 decisions.

Every decision has one of three types:

- **Policy (18).** The answer moves with a position. A decision decided by two policies
  (S5, V5) takes one field from each.
- **Rule (7).** The same answer at every position: S6, S7, R3, R7, L4, A4, A5. A rule
  marks the edge of a spectrum, for example that a single period's revenue annualized is
  never ARR. A company may depart from a rule, and the departure is recorded as a rule
  breach the deliverable states.
- **Convention (6).** No position decides it: the measurement window (S2), currency
  translation (V4), bridge classes (A1), acquired ARR (A2), the customer unit (A3) and
  the retention formula (A6). Each carries a default. Two further parameters sit beside
  them: the grace window in days (L3) and the document threshold for outlier contracts
  (L4). A convention no figure needs takes the value `none` and is not asked: the window
  is `point_in_time` while ARR is a contract snapshot.

An **override** is a decision the company settles differently from what its positions
derive. It carries a `reason` or a `cite`. A policy whose stated rules need many
overrides is not described by its position, so `arr_policy.py resolve` reports it as
incoherent and asks for the position instead.

## The file

One YAML file per company. `arr_policy.py resolve` writes it; `arr_policy.py approve`
stamps it; nothing else edits a saved policy.

```yaml
schema: countz-accounting/arr-policy@1
company: Demo DGII Corp
status: approved                  # draft until `approve`; any re-resolve returns it to draft
approved: {by: Jane Smith, at: 2026-09-24T22:22:32Z}
purpose: sell_side                # optional; the dial
documents:                        # where stated rules were read from
  - {path: /abs/ARR policy memo.pdf, title: ARR policy memo, FY2025}
policies:
  source: {position: contract, set_by: purpose}
  recurrence: {position: plus_services_warranty, set_by: inferred,
               evidence: "3 of 3 stated decisions (R4, R5, R6)"}
  lifecycle: {position: grace, set_by: answer}
  value: {position: net_current_step, set_by: purpose}
conventions:
  window: {value: point_in_time, set_by: not_needed, why: a contract snapshot at the date needs no window}
  fx: {value: prior_year_end_rate, set_by: default}
  # ... modification_classes, acquired, customer_unit, retention, grace_days, outlier_threshold_pct
decisions:
  S1: {value: contract, basis: derived}
  R6: {value: include, basis: override, derived: include_term_contracted,
       cite: "ARR policy memo p.2: warranty is ARR from shipment"}
  # ... all 31
```

- `set_by` on a position: `stated` (a document names the position), `inferred` (from the
  stated decisions it decides), `purpose`, `answer` (the user said so).
- `set_by` on a convention: `stated`, `answer`, `default` (proposed and approved as shown),
  `not_needed`.
- `basis` on a decision: `derived` (from its positions), `rule`, `convention`, `stated`
  (a document states it and it agrees with the positions), `override`.
- Values are the catalog's option ids. A composite decision (S5, R3, R5, R7, L2, L4, V1,
  V5, A2, A6) is a mapping of fields.

**Stated input.** A document's rules enter as a partial file: `company`, `documents`, and
under `decisions` each rule the document states, as `{value, basis: stated, cite,
quote}`. A document that names a position or a convention directly enters under
`policies` or `conventions` with `set_by: stated`. `resolve` does the rest.

## Where a policy lives

- **The library:** `$HOME/.countz-accounting/arr-policies/<company-slug>.yaml`, one
  approved policy per company, the file a later run reuses. The user may name another
  path.
- **In a run:** pinned at `<run_dir>/arr_policy.yaml` by
  `setup_run.py <run_dir> --arr-policy <file>`, which refuses a policy `arr_policy.py
  check` does not pass (complete and approved) and records its sha in
  `run.json.inputs.arr_policy`. A run pins one policy and never edits it. A change to the
  policy is a new approval and a new run.

## How a run uses it

A recipe that computes ARR, recurring revenue, retention, churn or an ARR bridge declares
`arr_policy` in its frontmatter (`RECIPE_FORMAT.md` § The document). The relay settles
it through the `create-arr-policy` skill before the plan is drafted
(`PLAYBOOK_RECIPES.md` § 1 and § 2). Its value in `declared` is the pinned path.

- The plan writes `params.arr_policy` into every step whose recipe section names it.
- A worker reads the decisions it applies by id (`decisions.S1.value`), never from a
  default of its own. The step's record cites the decision id beside each figure the
  decision moves, so the reader can trace a number to the policy line that produced it.
- The workbook's Basis of Preparation states the purpose, the four positions, the
  conventions, and every override and rule breach, each with its reason or citation.
- Where the records cannot apply a decision as written (a policy counts committed
  consumption, and no record carries the commitment), the figure is withheld with the
  `D.`. The decision is never re-made in the run.
