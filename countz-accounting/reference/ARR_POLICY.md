# The ARR policy

No accounting standard defines annual recurring revenue. Two analysts working from the
same records compute different ARR, because a definition is a bundle of choices: which
record sets the amount, what counts as recurring, when a customer enters and leaves,
and at what price. A run that computes ARR therefore computes it under a written policy
the company approved, and states that policy beside every figure that depends on it.

This document is the contract for that policy. The catalog itself (every purpose,
position, convention, decision, option and derivation) has one home,
`scripts/arr_policy.py`, which reads and writes YAML, so it always runs through the
plugin's pinned libraries. Print the catalog with:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/arr_policy.py catalog
```

Below, `arr_policy.py` means that same invocation.

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
# ARR policy. Before you use any value in this file, read how it is applied:
#   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/ARR_POLICY.md "Applying the policy"
# ...
schema: countz-accounting/arr-policy@1
apply_per: ${CLAUDE_PLUGIN_ROOT}/reference/ARR_POLICY.md § Applying the policy
company: Acme Corp
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
instructions:                     # free text: how the decisions apply to this business
  - id: I1
    text: >-
      Certificate ARR is coverage per protected domain per year: a plan counts its annual
      price once, however many certificates are reissued under it.
    applies_to: [S5]
    source: inferred              # user | stated | inferred
    basis: "S5 timing is coverage_per_year; a reissue carries no price"
    added: {at: 2026-09-25T10:02:11Z, in: revenue-analysis-acme.20260925-095811}
```

- The header comment and `apply_per` point whoever opens the file to § Applying the
  policy before any value is used. `arr_policy.py` writes both on every save, so they
  survive every resolve, amend and approval.
- `set_by` on a position: `stated` (a document names the position), `inferred` (from the
  stated decisions it decides), `purpose`, `answer` (the user said so).
- `set_by` on a convention: `stated`, `answer`, `default` (proposed and approved as shown),
  `not_needed`.
- `basis` on a decision: `derived` (from its positions), `rule`, `convention`, `stated`
  (a document states it and it agrees with the positions), `override`.
- Values are the catalog's option ids. A composite decision (S5, R3, R5, R7, L2, L4, V1,
  V5, A2, A6) is a mapping of fields.
- `instructions` are free text (§ Instructions). `source: stated` carries a `cite`,
  `source: inferred` a `basis`; `applies_to` names the decisions an instruction refines,
  or is empty for one that applies throughout.

**Stated input.** A document's rules enter as a partial file: `company`, `documents`, and
under `decisions` each rule the document states, as `{value, basis: stated, cite,
quote}`. A document that names a position or a convention directly enters under
`policies` or `conventions` with `set_by: stated`. A stated rule no option can express
enters under `instructions` with `source: stated` and its `cite`. `resolve` does the rest.

## Instructions

The 31 decisions are generic: they name choices every recurring-revenue business faces.
A business also has its own products, contracts and channels, and how a decision applies
to them often cannot be an option id. For example: that a certificate plan counts once
however many reissues it carries, that a reseller's prepaid balance is not ARR until it
is drawn, or that a usage tier resetting monthly is annualized at twelve times the tier.
An **instruction** records that in plain English.

- **An instruction refines a decision; it never contradicts one.** It says how a
  decision's value applies to this business's records. To change the value itself, the
  decision is overridden, with its reason. An instruction that reads against its
  decision's value is resolved by the user before the policy is approved.
- **Three sources.** `stated`: a company document says it, with a `cite`. `user`: the
  user said it, in create-arr-policy or in answer to a question. `inferred`: it follows
  from the policy's own settings, with a `basis` naming them. Every instruction is
  approved with the policy, whatever its source.
- **Added when needed.** create-arr-policy records the ones the company's documents
  state and the user gives. A run adds the ones its steps meet, and saves them to the
  library policy (§ Applying the policy, steps 5 and 6).

## Where a policy lives

- **The library:** `$HOME/.countz-accounting/arr-policies/<company-slug>.yaml`, one
  approved policy per company, the file a later run reuses. The user may name another
  path.
- **In a run:** pinned at `<run_dir>/arr_policy.yaml` by
  `setup_run.py <run_dir> --arr-policy <file>`, which refuses a policy `arr_policy.py
  check` does not pass (complete and approved) and records its sha in
  `run.json.inputs.arr_policy`. The pinned file is never edited. A policy amended during
  the run (§ Applying the policy, step 6) replaces it: any approved policy before the plan
  is approved; after that, only one that adds instructions and changes no position,
  convention or decision (`arr_policy.py same-core`). Any other change is a new run.

## How a run carries it

A recipe that computes ARR, recurring revenue, retention, churn or an ARR bridge declares
`arr_policy` in its frontmatter (`RECIPE_FORMAT.md` § The document). The relay settles
it through the `create-arr-policy` skill and pins it before the plan is drafted
(`PLAYBOOK_RECIPES.md` § 2), and the plan writes its path into the `params.arr_policy`
of every step the recipe names. From there, § Applying the policy governs.

## Applying the policy

This section is the one statement of how an ARR policy is applied. The worker computing a
figure, the critic reviewing it and the relay recording what they find all follow it.
The worker and the critic reach it through the recipe, which they read whole and which
routes every step carrying `params.arr_policy` here (`RECIPE_FORMAT.md` § The
document), and through the header of the policy file itself. The relay reaches step 6
through `PLAYBOOK_RECIPES.md` § 4.

**When.** Every step whose `params` carry `arr_policy`, for every figure, population or
ruling that a decision could move. The critic applies it to every such step it reviews:
treatment that departs from what this section requires, or a ruling that fails step 5's
tests, is a `judgment` finding, graded by the amount it moves.

1. **Read the policy.** Run `arr_policy.py render <params.arr_policy>`. It prints the positions, the conventions, all 31 decisions and
   the instructions.
2. **State what applies, before computing.** Name the decisions the step applies, each
   with its value, and the instructions that refine them: every instruction whose
   `applies_to` names one of those decisions, and every instruction whose `applies_to`
   is empty.
3. **Apply them as written.** A decision's value governs, and its instructions govern how
   that value meets this company's rows. Never substitute a default of your own, and
   never re-make a decision. Where the records cannot carry a decision as written (the
   policy counts a committed consumption minimum and no record carries the commitment),
   withhold the figure with the `D.` naming the record that would allow it.
4. **Cite the policy.** Beside every figure a decision or instruction moves, in the
   figure's description and in the check's narrative, cite their ids: `S5, I1`. The
   reader traces the number to the policy line that produced it.
5. **Settle what is still pending, lazily.** A question is pending when this company's
   records raise it and no decision value, override or instruction answers it: a
   certificate reissued under one plan, a prepaid balance drawn down per purchase, a
   usage tier that resets monthly. Settle it when you meet it, never ahead of need:
   - **Infer it when the policy decides it.** Infer when the positions, conventions and
     decisions admit one reading, or when the readings differ by less than materiality
     (`DOCTRINE.md` § Materiality). A reading that contradicts a decision's value is
     never inferred. Append it to `<run_dir>/arr_policy/gaps-<check_id>.yaml` under
     `inferred` as `{id: I.<check_id>.<n>, text, applies_to, basis}`, where `basis` names
     the settings it follows from. Apply it, cite its id, and go on.
   - **Ask only when it does not.** Where two readings each fit the policy and would move a
     figure beyond materiality, append the question under `questions` as `{id:
     Q.<check_id>.<n>, question, why, readings, applies_to}`. Compute everything the
     question does not move. Then finish `blocked`, with one blocker per question whose
     `what` begins `ARR policy question Q.<check_id>.<n>` and whose `effect` names the
     figures held for the answer. A step cannot ask the user; the relay does (step 6).
   - **Review the ruling.** The critic tests each inferred ruling like any other. It
     checks that the ruling follows from the basis it names, contradicts no decision's
     value, and is not a material choice that should have been asked.
6. **Record the addition in the policy (the relay).** After each wave's `record`, and
   before the next wave launches, the relay reads the steps' `gaps-*.yaml`:
   - **A question stops the run.** A question is open until `answers.yaml` carries its
     id. Put every open question to the user in one message, with its readings and the
     evidence that raised it. Write the answers to
     `<run_dir>/arr_policy/answers.yaml` (`{Q.<check_id>.<n>: "<their words>"}`).
   - **An inferred addition does not stop the run.** Collect it, and put it to the user
     for confirmation with the review's findings. A correction is an answer, and re-runs
     the steps it moves.
   - **Amend and approve.** Whenever answers or confirmations are in hand, run
     `arr_policy.py amend <run_dir>/arr_policy.yaml --gaps <run_dir>/arr_policy/gaps-*.yaml
     --answers <run_dir>/arr_policy/answers.yaml --run <run id> --out
     <run_dir>/arr_policy/amended.yaml`. Show the § Instructions of its render, then
     approve and save it to the library path the pinned policy came from
     (`run.json.inputs.arr_policy.source`): `arr_policy.py approve --by "<the user's
     name>" --out <that path>`. Pin it again with `setup_run.py <run_dir> --arr-policy
     <that path>`, and re-dispatch each step that blocked on a question now answered
     (`run_state.py dispatch <run_dir> --checks <check id>`). `amend` skips an addition
     the policy already carries, so the gap files are passed whole every time.
   - **Instructions accumulate.** Every addition lands in the library policy, so the next
     run over the same company starts with it and does not ask again.

**The deliverable** states the policy on the Basis of Preparation: the purpose, the four
positions, the conventions, every override and rule breach with its reason or citation,
and every instruction with its source.
