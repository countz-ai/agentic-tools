# The ARR policy

No accounting standard defines annual recurring revenue. A definition is a set of
choices: which record sets the amount, what counts as recurring, when a customer enters
and leaves, and at what price. A run computes ARR under a written policy the company
approved, and states that policy beside every figure that depends on it.

This document is the contract for that policy. The catalog itself (every purpose,
position, convention, decision, option and derivation) lives only in
`scripts/arr_policy.py`; run it through the plugin's pinned libraries. Print the catalog
with:

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
`sell_side` or `buy_side`. Ask it first: it settles the 18 policy decisions.

Every decision has one of three types:

- **Policy (18).** The answer moves with a position. A decision decided by two policies
  (S5, L2, V1, V5) takes each of its two fields from one of them.
- **Rule (7).** The same answer at every position: S6, S7, R3, R7, L4, A4, A5. A rule
  marks the edge of a spectrum, for example that a single period's revenue annualized is
  never ARR. A company may depart from a rule, and the departure is recorded as a rule
  breach the deliverable states.
- **Convention (6).** No position decides it: the measurement window (S2), currency
  translation (V4), bridge classes (A1), acquired ARR (A2), the customer unit (A3) and
  the retention formula (A6). Each carries a default. Three further parameters sit beside
  them: the event a new stream enters ARR from and the months after it (L1), and the
  document threshold for outlier contracts (L4). The window is `point_in_time` exactly
  when no decision measures an amount from a flow (§ Computing ARR, S2), and is then not
  asked. `resolve` refuses any other window until the user settles it.

An **override** is a decision the company settles differently from what its positions
derive. It carries a `reason` or a `cite`. A policy whose stated rules need many
overrides is not described by its position, so `arr_policy.py resolve` reports it as
incoherent and asks for the position instead.

## The file

One YAML file per company. `arr_policy.py resolve` writes it; `arr_policy.py approve`
stamps it; nothing else edits a saved policy. `approve` refuses a file that resolving
again would change (one edited after `resolve`, or resolved under an older catalog), and
stamps a digest of what the policy settles. `arr_policy.py check` passes only a file that
resolving again would not change and that matches its digest.

```yaml
# ARR policy. Before you use any value in this file, read how it is applied:
#   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/ARR_POLICY.md "Applying the policy"
# ...
schema: countz-accounting/arr-policy@1
apply_per: ${CLAUDE_PLUGIN_ROOT}/reference/ARR_POLICY.md § Applying the policy
company: Acme Corp
status: approved                  # draft until `approve`; any re-resolve returns it to draft
approved: {by: Jane Smith, at: 2026-09-24T22:22:32Z, digest: 3f9a0c6e1b2d4a57}
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
  fx: {value: closing_spot_rate, set_by: default}
  # ... modification_classes, acquired, customer_unit, retention, entry_event, signing_lag_months, outlier_threshold_pct
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
  `not_needed`. A composite convention stated in part takes the default for its other
  fields and lists them in `default_fields`.
- `basis` on a decision: `derived` (from its positions), `rule`, `convention`, `stated`
  (a document states it and it agrees with the positions), `override`. A composite
  decision stated in part takes the derivation for its other fields and lists them in
  `derived_fields`; every resolve derives them again, and they never count as stated. A
  departure from a rule, or from a field the catalog fixes (R5 `outright_sales`), carries
  `rule_breach: true`.
- Values are the catalog's option ids. A composite decision (S5, R3, R5, R7, L2, L3, L4,
  V1, V5, A2, A6) is a mapping of fields. A number of months is 0 or more; a percentage is
  0 to 100, or `none`.
- `instructions` are free text (§ Instructions). `source: stated` carries a `cite`,
  `source: inferred` a `basis`; `applies_to` names the decisions an instruction refines,
  or is empty for one that applies throughout.

**Stated input.** A document's rules enter as a partial file: `company`, `documents`, and
under `decisions` each rule the document states, as `{value, basis: stated, cite,
quote}`. A document that names a position or a convention directly enters under
`policies` or `conventions` with `set_by: stated`. The convention decisions (S2, V4, A1,
A2, A3, A6) and L4's `document_threshold_pct` hold their convention's value; stated
under both `decisions` and `conventions`, the two values must agree. A stated rule no
option can express enters under `instructions` with `source: stated` and its `cite`.
`resolve` does the rest. It prints each contradiction it cannot settle as an `ERROR` for
the user to rule on.

## Instructions

The 31 decisions are generic. How a decision applies to a business's own products,
contracts and channels often cannot be an option id; an **instruction** records it in
plain English. Examples: a certificate plan counts once however many reissues it
carries; a reseller's prepaid balance is not ARR until it is drawn; a usage tier that
resets monthly is annualized at twelve times the tier.

- **An instruction refines a decision; it never contradicts one.** It says how a
  decision's value applies to this business's records. To change the value itself,
  override the decision with its reason. The user resolves an instruction that reads
  against its decision's value before the policy is approved.
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
  check` does not pass (complete, approved, unchanged since approval) and records its
  sha in `run.json.inputs.arr_policy`. The pinned file is never edited. A policy amended during
  the run (§ Applying the policy, step 6) replaces it: any approved policy before the plan
  is approved; after that, only one that adds instructions and changes no position,
  convention or decision (`arr_policy.py same-core`). Any other change is a new run.

## How a run carries it

A recipe that computes ARR, recurring revenue, retention, churn or an ARR bridge declares
`arr_policy` in its frontmatter (`RECIPE_FORMAT.md` § The document). The relay settles
it through the `create-arr-policy` skill and pins it before the plan is drafted
(`PLAYBOOK_RECIPES.md` § 2), and the plan writes its path into the `params.arr_policy`
of every step the recipe names. From there, § Applying the policy governs, and
§ Computing ARR says how each value becomes a figure.

## Applying the policy

This section is the one statement of how an ARR policy is applied. The worker computing a
figure, the critic reviewing it and the relay recording what they find all follow it.

**When.** Every step whose `params` carry `arr_policy`, for every figure, population or
ruling that a decision could move. The critic applies it to every such step it reviews:
treatment that departs from what this section requires, or a ruling that fails step 5's
tests, is a `judgment` finding, graded by the amount it moves.

1. **Read the policy.** Run `arr_policy.py render <params.arr_policy>`. It prints the
   positions, the conventions, all 31 decisions and the instructions.
2. **State what applies, before computing.** Name the decisions the step applies, each
   with its value, and the instructions that refine them: every instruction whose
   `applies_to` names one of those decisions, and every instruction whose `applies_to`
   is empty.
3. **Apply them as written.** A decision's value governs, computed as § Computing ARR
   states for that value, and its instructions govern how that value meets this
   company's rows. Never substitute a default of your own, and
   never re-make a decision. Where the records cannot carry a decision as written (the
   policy counts a committed consumption minimum and no record carries the commitment),
   withhold the figure with the `D.` naming the record that would allow it.
4. **Cite the policy.** Beside every figure a decision or instruction moves, in the
   figure's description and in the check's narrative, cite their ids: `S5, I1`.
5. **Settle what is still pending, lazily.** A question is pending when this company's
   records raise it and no decision value, override or instruction answers it: a
   certificate reissued under one plan, a prepaid balance drawn down per purchase, a
   usage tier that resets monthly. Settle it when you meet it, never ahead of need:
   - **Infer it when the policy decides it.** Infer when the positions, conventions and
     decisions admit one reading, or when the readings differ by less than materiality
     (`DOCTRINE.md` § Materiality). A reading that contradicts a decision's value is
     never inferred. Append it to `<run_dir>/arr_policy/gaps-<check_id>.yaml` under
     `inferred` as `{id: I.<check_id>.<n>, text, applies_to, basis}`, where `basis` names
     the settings it follows from. Apply it, cite its id, and go on. An id is permanent
     across every run over the same company: number `n` above the highest `n` the policy
     carries for that check id under `I.` or `IQ.`. `amend` refuses an id the policy
     already gives to another text.
   - **Ask only when it does not.** Where two readings each fit the policy and would move a
     figure beyond materiality, append the question under `questions` as `{id:
     Q.<check_id>.<n>, question, why, readings, applies_to}`, numbered the same way. Its
     answer enters the policy as instruction `IQ.<check_id>.<n>`. Compute everything the
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

**The deliverable** states the policy on the Basis of Preparation: the purpose, the four
positions, the conventions, every override and rule breach with its reason or citation,
and every instruction with its source.

## Computing ARR

This section is the one statement of how ARR, its movements and its retention are
computed from a policy's values, for every decision and every option; the plugin's tests
fail when a catalog option has no rule below. A recipe says where the figures land (its
cube, its bridge, its tabs) and which decisions each step turns on, never how a
decision's value becomes a number. An instruction refines these rules for one company's
records (§ Instructions); a question neither reaches is settled per § Applying the
policy, step 5.

### ARR at a date

**ARR at a date** is the sum, over the customers in force at that date, of the
annualized value of their recurring streams: the streams the recurrence decisions count
(R1–R7), in force per the lifecycle decisions (L1–L6), measured from the record S1
names, at the price the value decisions set (V1–V3, V5), in the reporting currency per
V4. Non-recurring revenue, contra revenue other than as V3 nets it, taxes and
pass-through amounts carry no ARR. A figure is measured at a month end, and a month
counts whole or not at all: a stream carries its full value at every month end from the
month it enters ARR to the last month end it is carried (§ When a stream is in force).
No contract value is prorated by days. Under a run-rate S1 a month's revenue is what the
records show, a month served in part included, annualized as it stands.

**S1 · ARR basis.** The record the amount is taken from.
- `contract`: the contract's annual value as modified by the date (§ Modifications): a
  monthly figure times twelve, a quarterly figure times four, a semi-annual figure times
  two, a multi-year or prepaid figure per S3, a term licence per S4.
- `all_agree`: the `contract` value, where the invoice for the stream's current service
  period and the cash applied to it agree with it. Cash agrees when the invoice is paid,
  or is not yet due at the date. Where the three disagree, the stream is carried at the
  lowest of them and the difference is recorded per contract; a stream with no invoice
  for its current service period carries no ARR at that date.
- `recognized_run_rate`: the recurring revenue recognized in the S2 window, annualized.
- `billed_spread`: each recurring billing spread evenly over the service period it
  covers, and the spread amounts falling in the S2 window annualized.
- `contract_else_billed`: two legs, settled per customer (the A3 unit) and product at each
  date. A product the customer holds under a contract in force that prices it at a fixed
  recurring amount or a committed minimum, or under a contract L3 still carries past its
  end, is on the contract leg: the contract takes the `contract` value, R1 and R2 govern
  its usage and overage, and no invoice for that product outside the contract carries ARR
  for the customer. A product the customer holds under no such contract, bought with no
  contract or under an uncommitted contract (one that states neither a fixed recurring
  price nor a committed minimum), is on the billed leg: its ARR is the sum of the
  customer's invoice lines for it dated in the S2 window, usage included, net of the
  credit notes against them. The sum is taken as it stands: never scaled up for a
  customer or product that started inside the window, and not withheld where the records
  reach back fewer months than the window. A prepaid balance counts as it is drawn down in
  the window, never at its purchase invoice (S6), and an invoice billed under a
  fixed-price or committed contract never counts on the billed leg. A product on the
  billed leg churns when its window holds no invoice for it. The customer's ARR is the sum
  of its products on both legs. A product moving between legs is neither churn nor new:
  the change in its ARR is expansion or contraction, and a bridge by leg shows the amount
  moved as a transfer between legs that nets to zero in total. Every figure carries the
  leg that measured it (`contract` or `billed`), and every ARR figure, bridge movement and
  retention measure is reported by leg as well as in total; a customer holding ARR on
  both legs counts as a logo in each leg and once in the total.

**S2 · Measurement window.** How a flow is annualized; it applies to a run-rate S1, to
usage R1 and R2 count, and to S3, S4 and S5 wherever they take a recognized amount.
- `point_in_time`: no window; the value in force at the date. The window is
  `point_in_time` exactly when the policy takes none of these options, each of which
  measures an amount from a flow: S1 `recognized_run_rate`, `billed_spread` or
  `contract_else_billed`; S3 `ratable_revenue`; S4 `recognized_revenue`; S5 `timing`
  `at_issuance`; R1 `commit_plus_usage`; R2 `include`.
- `month_x12`: the month ending at the date, times twelve.
- `trailing_3_months`: the three months ending at the date, times four.
- `trailing_12_months`: the twelve months ending at the date.

A stream that started inside the window is annualized over the months it was served,
never over months before it existed.

**S3 · Multi-year and prepaid contracts.**
- `annualized_contract`: total contract value, as modified, divided by the term in
  years; a prepayment is spread over the years it covers.
- `ratable_revenue`: the revenue recognized on the contract in the S2 window, annualized.

**S4 · Term or perpetual licences recognized upfront.**
- `annualized_contract`: a term licence's fee divided by its term in years, from its
  start. A perpetual licence has no term and carries no ARR; its support and
  maintenance are streams of their own.
- `recognized_revenue`: the licence revenue recognized in the S2 window, annualized, so
  the month of recognition carries it.

**S5 · Point-in-time products bought repeatedly.** `timing`:
- `coverage_per_year`: the annual price of the coverage an item gives, in force for its
  coverage period from issuance; a reissue within the period adds nothing.
- `at_issuance`: the price at issuance, in the month issued, annualized over S2.

`one_off`, which purchases count at all:
- `exclude`: none.
- `after_first_renewal`: from the customer's first repurchase of the same product,
  counted from that month; the first purchase is never restated into ARR.
- `include`: from the first purchase.

**S6 · Prepaid funds and drawdown balances.** `not_arr`: a prepaid balance carries no
ARR; drawdowns against it are usage, counted per R1 and R2. `annualize_balance` (a rule
breach): the balance divided by the term it covers.

**S7 · Revenue run-rate labeled as ARR.** `not_arr`: a period's total revenue
annualized, recurring and non-recurring together, is never ARR; a run-rate S1 annualizes
only the streams R1–R7 count. `report_as_arr` (a rule breach): management's revenue
run-rate is carried as ARR, and the deliverable says so beside every figure.

**R1 · Consumption with a committed minimum.**
- `exclude`: consumption carries no ARR, committed or not.
- `commit_only`: the committed annual minimum, annualized as a contract (S3); usage
  above it carries none.
- `commit_plus_usage`: the commitment, plus usage above it and usage with no commitment,
  annualized over S2 in the months the usage occurred.

**R2 · Overage and true-ups billed in arrears.** `include`: annualized over S2 in the
months of the usage billed, never the month of the invoice. `exclude`: none.

**R3 · Professional services and setup bundled in the deal.** `treatment`: `exclude`
takes them out of the contract value; `include` (a rule breach) leaves them in.
`carve_out`, how the excluded amount is measured:
- `contract_line_then_ssp`: the contract's own line price, and its standalone selling
  price where the contract does not price it separately.
- `contract_line`: the contract's line price only; unpriced services stay in the value.
- `ssp_allocation`: the bundle allocated by standalone selling price.

**R4 · Recurring services** (premium support, managed services, data plans). `include`
counts them as recurring streams; `exclude` does not.

**R5 · Hardware.** `outright_sales`: `exclude`, or `include` (a breach of the fixed
field). `bundled`, equipment priced into a subscription: `include` leaves it in the
subscription value; `exclude` carves it out as R3's `carve_out` measures.

**R6 · Maintenance or warranty attached to hardware.**
- `exclude`: none.
- `include_term_contracted`: only maintenance contracted for a term at a stated price.
- `include`: that, and maintenance renewed and billed without a term contract.

**R7 · Pilots, trials, break clauses and refund windows.** `pilots`: `exclude` keeps a
pilot or trial out until it converts to a paid contract, counted from conversion;
`include` counts it from its start. `refund_window`: `count_after_window` counts a
contract with a refund window or break clause from the month the window lapses unused;
`count_at_booking` counts it from its start.

### When a stream is in force

A stream enters ARR in a whole month, as L1 dates it, and carries its full value from
that month end. It leaves as L2, L3, L5 and L6 date it.

**L1 · Signed but not started, and when a new stream enters.** A new stream is a
customer's first contract for a product; a renewal, extension or modification of a
stream already in ARR enters nothing, and its value changes per § Modifications. A new
stream enters ARR in the latest of these months:
- the entry month plus `signing_lag_months`. The entry month is the month of the event
  the `entry_event` convention names: `signed`, when the contract is signed, or
  `booked`, when the order is recorded as booked in the company's records. A contract
  cancelled before the month it would enter ARR never enters ARR, and is neither new
  nor churn;
- its service start month, under `exclude_report_separately`, where a signed contract
  not yet started is contracted ARR, carried beside ARR on its own line until then.
  Under `include` the service start sets no floor: the stream is ARR from the lag alone;
- the end customer's activation month, where V5 `start` is `end_customer_activation`;
- the month its refund window or break clause lapses, where R7 `refund_window` is
  `count_after_window`.

Where the records carry no date for the `entry_event`, the other event's date stands in
for it, then the service start date, and the row records which did.

**L2 · Churn timing, and which termination record wins.** `churn_at`: `at_notice` — the
stream leaves in the month a non-renewal or termination notice is received, though it
is still served; `effective_date` — it leaves at the effective end.
`conflicting_records`, where two records date a contract's end differently, names the
one that governs; the other is recorded beside it:
- `earliest_end`: the earliest end any record shows.
- `contract_as_amended`: the contract and every amendment to it (an extension, an early
  termination, a change order), wherever the data room holds them: signed documents, an
  amendment or modification log, CRM contract records. Where they disagree with each
  other, the latest-dated amendment governs; a date only a CRM or billing record shows,
  with no contract document behind it, is recorded beside the contract's.

Where no record dates a contract's end, the end is a pending question. A stream measured
from revenue or billing rather than a contract (a run-rate S1, the billed leg of
`contract_else_billed`) has no end date to settle: it leaves ARR when its window holds
none.

**L3 · Renewal gaps, holdover and grace periods.** The last month end a contract is
carried, and so the month it churns. Its end is dated by L2. `treatment`:
- `grace_window`: the contract is carried at every month end on or before its end date,
  and at the first `grace_months` month ends after it. Examples: at `0`, a contract
  ending on the 15th is out at that month's end, and one ending on the month's last day
  is carried at it; at `1`, the month the contract ends in part-way is carried whole; at
  `3`, a late renewal has three months to arrive.
- `continuation`: the contract is carried at every month end on or before its end date,
  and after it at every month end it is still billed or recognized for; then at the
  first `grace_months` month ends after the last of those.
- `until_renewal`: the contract is carried at every month end on or before its end date.
  Where the records show its renewal, booked before or after its end, it is also carried
  at every month end after its end until the renewal's first month in ARR, however long
  the gap, so the gap is neither churn nor reinstatement. Where they show none, it is
  carried at the first `grace_months` month ends after its end, and then churns. A
  renewal counts only once the records show it: at the latest month ends, a contract
  whose renewal is not yet booked churns, and the months are restated when one is.
- `while_paying`: the contract is carried at every month end on or before its end date,
  and after it at every month end that falls in a service period the customer is still
  invoiced for, at its last contract value as modified, never at a price only the
  invoices show. The customer has not churned, and a renewal the records show takes over
  from its first month in ARR as a continuation. Once no service period after the end
  date is invoiced, the stream is carried at the first `grace_months` month ends after
  the last invoiced period, and then churns. Unlike `continuation`, a month recognized
  but not invoiced does not carry it.

A contract carried past its end date is carried at its last value, as modified. A
renewal that starts before the first month end the contract is no longer carried at is
a continuation; a successor that starts after it is churn in that month followed by
reinstatement in the successor's. Every month end a contract is carried past its end
date is flagged with the rule and the record that carry it.

**L4 · Outlier and short-lived contracts.** `short_terminated`, a contract terminated
within its first twelve months of service: `service_months_only` carries it at the
monthly value of the months it served, never annualized beyond them; `annualize` (a
rule breach) carries it at its annual value while in force; `exclude` (a rule breach)
carries it at no month end, those before its termination included: it never enters ARR,
and is neither new nor churn. Measured on the records as they stand, so a month reported
before the termination was recorded is restated. `document_threshold_pct` (the
`outlier_threshold_pct` convention): a contract whose annualized value exceeds that
share of total ARR at the first date it is in force enters ARR only with the signed
order form or amendment that evidences it; without one it is withheld with its `D.`. At
`none`, no contract is held to this test.

**L5 · Stub, co-term and month-to-month contracts.**
- `exclude`: none of them carries ARR.
- `annualize_coterm_only`: a stub co-termed to a parent contract is annualized at its
  period rate; month-to-month carries none.
- `annualize_all`: both, month-to-month at its monthly value times twelve.

**L6 · Collectability and bad debt.**
- `exclude_written_off_and_90_days`: the customer leaves ARR in the month its receivable
  is written off or first falls more than 90 days past due.
- `exclude_written_off`: in the month it is written off.
- `include_until_terminated`: collectability moves nothing; the contract governs.

A customer excluded for collectability that pays current returns as a reinstatement.

### Price and currency

**V1 · Ramps and escalators.** `step`: `current_step` — the price of the step in force at
the date; `term_average` — total contracted value over the term divided by its years.
`billing_only_step_ups`, a step-up billing shows and the contract does not:
`require_contract_evidence` counts it only with a contract or amendment that states it;
`as_billed` counts it from the month billed.

**V2 · Discounts and free months.**
- `net_current`: net of the discounts in force at the date; a free month is valued at
  zero while it runs.
- `net_current_free_months_at_rate`: net of the discounts in force at the date, as
  `net_current`, but a free month is valued at the net rate of the first paid month after
  it, as a contract signed and not yet started is valued at its first paid month.
- `net_term_average`: the term's total net value divided by its years, free months
  spread across it.
- `list_price`: before discounts.

**V3 · Credits, refunds and SLA credits.**
- `net_all_credits`: every credit, refund and SLA credit issued against a recurring
  stream in the twelve months to the date reduces its ARR by that amount.
- `net_recurring_credits`: only a credit that recurs each billing period (a standing
  concession), at its annualized amount.
- `before_credits`: none.

**V4 · Currency translation.** Every rate is taken from the rate table the data room
carries, never fetched from outside it; a rate the table does not carry withholds the
figures that need it with the `D.`.
- `prior_year_end_rate`: the closing rate at the prior fiscal year end, held for every
  date in the year.
- `start_of_year_rate`: the rate on the first day of the fiscal year, held for the year.
- `contract_signing_rate`: the rate on the contract's signing date, held for its term.
- `period_average_rate`: the average rate of the month ending at the date.
- `closing_spot_rate`: the rate at the date.

**V5 · Channel.** `price`: `net_of_channel` — the price the reseller pays the company;
`gross` — the end customer's price, where a record carries it. `start`:
`end_customer_activation` — a resold stream enters when the end customer activates;
`sell_in` — when the company sells to the reseller.

### Modifications

A contract's value at a date is its value as modified by that date. Every price,
quantity or scope change the records carry — an amendment, a change order, a price
increase or concession, an upgrade or downgrade on a contract-modification register —
changes its annualized value from the month the change takes effect, and the ARR at a
date carries every change effective on or before it. A modification that terminates a
contract early ends it at the date L2 names; one that extends the term moves its end.
Where a modification states an original value that disagrees with the register's value
for the same contract, the change the modification records is applied to the register's
value and the disagreement is recorded with both figures; where the records carry the
modified value but not the change, that value governs from its effective month.

### The customer, and how ARR moves

**A3 · Customer unit.** The unit every logo count, bridge movement and retention measure
is taken on.
- `root_parent`: where a record names a parent, the chain is followed upward to the
  party that names no parent, and that root is the customer every party beneath it
  resolves to, however many levels the chain runs. A subsidiary that starts buying while
  its root already buys is cross-sell; one that stops while its root still buys is
  contraction.
- `bill_to`: the bill-to party is the customer; its root is carried as a dimension.
- `payer`: the paying party is the customer; its root is carried as a dimension.

**The bridge.** Month over month, at the A3 unit × product grain: opening ARR; **new**,
a unit with no ARR in the prior month and none in the twelve months before it;
**reinstated**, a unit returning as A5 says; **expansion** and **contraction**, classed
by A1; **churn**, a unit whose ARR falls to zero, dated per L2 and L3; **reallocated**,
per A4; **acquired** and **divested**, per A2; **fx**, the change in translated ARR at
constant contracts, which V4 decides (under a rate held for the year it arises only at
the year's turn); closing ARR. Every movement is classified from the two months'
values, and one the values do not settle is an exception at its amount.

**A1 · Mid-term modifications: bridge classes.** Whether expansion and contraction are
split into fixed classes.
- `expansion_contraction`: no split. A same-customer increase is expansion and a
  decrease is contraction. Any finer analysis of why a customer's ARR moved belongs to
  the recipe, on the dimensions the data room carries.
- `register_type`: the class the modification register gives the change; a change with
  no register row is classed by `price_vs_quantity`.
- `price_vs_quantity`: the same product and quantity at another unit price is price
  uplift or price concession; a change in quantity is upsell or downsell; a product the
  unit did not hold in the prior month is cross-sell.

**A2 · Acquired ARR and organic growth.** The acquired entity's customers are tagged
from `entry` — `close_date`, the month of close, or `first_full_month`, the first full
month after it — and their ARR is booked as **acquired** in that month. For
`window_months` from entry their movements sit in an acquired sub-group, after which
they are organic. A customer the acquired entity did not carry at close is organic from
its first month. Organic growth is closing ARR less opening ARR less acquired ARR; a
divestiture is the mirror, the divested customers leaving as **divested** in the month
of sale.

**A4 · Reallocations between customers.** `not_churn_with_evidence`: revenue moving
between customer ids with a record evidencing the move (an assignment, a merger, a
re-papering) is **reallocated**, neither churn nor new, on its own line netting to zero;
without the record, it is booked as it happened and sized as an open item.
`as_recorded` (a rule breach): every such move is churn and new.

**A5 · Opening base and reactivation.** `opening`: a unit in ARR at the opening of the
first period measured is opening base, never new, and a unit returning within twelve
months of its churn is **reinstated**. `new` (a rule breach): every returning unit is
new.

### Retention

**A6 · Net and gross revenue retention.** The cohort is the units, at `grain`, that
carry ARR twelve months before the date. `basis`:
- `point_to_point_arr`: gross revenue retention is the cohort's opening ARR less its
  churn and contraction over the twelve months, over its opening ARR; net revenue
  retention is the cohort's closing ARR, expansion included, over the same opening.
- `trailing_12m_revenue`: the same, on the cohort's recurring revenue in the twelve
  months to the date over its recurring revenue in the twelve months before.

`grain`: `customer` takes the cohort at the A3 unit, so cross-sell to a cohort member is
expansion; `customer_product` takes it at unit × product, so a product not held at the
opening is outside the cohort. `grr_cap`: `per_customer` caps each member's retained
ARR at its own opening before summing, so one member's expansion never offsets
another's contraction; `none` caps only the cohort's total at its opening.

Logo retention is the count of cohort units still carrying ARR at the date over the
count at the opening. Where the records reach fewer than twelve months before a date,
its retention is withheld with its `D.`, never computed on a short cohort.

### Management's definition

Where the data room states management's ARR definition, it is read against the policy
decision by decision, and every difference is named by decision id before any figure is
compared. A definition that is not stated is a `Q.`.
