# VALIDATION

What `check-review` validates, in what order, and the shape of the finding it writes.
This file is the whole scope; no other file adds to it.

## Prose checking

Every metric number in reader-facing text is checked by script, never by reading. Run
both gates over everything that has landed:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_prose.py <tab-or-workbook> --run-dir <run_dir> \
    [--allow <file carrying declared tolerances>]
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_report.py <deck>   # once a report has landed
```

`check_prose.py` takes the tabs and the workbook; `check_report.py` takes the deck
(`REPORT.md` § 5). The report step runs both before it seals; run them again yourself.
Every extracted number must agree with a ledger value within rounding tolerance. Any that does not is a blocking
finding.

## The validation scope

After the mechanical gates, validate eight things, in this order.

1. **Foot the tables.** Every table in the checks' records and tabs sums to the totals it
   displays. Where two tables state the same quantity, e.g. a statement total restated in
   a tab, check that they agree.
2. **Re-perform the significant claims.** Each check's headline result, the largest
   differences and their sides, named exceptions, the largest reconciling items, and
   anything the reader would quote onward. Agree each to its cited source in the user's
   own files, never to a derived table.
3. **Sample 20 items from the rest.** Match rows, exception rows, traced items and prose
   claims the first two parts did not reach, drawn across the checks under review. Agree
   each to its cited source.
4. **Read the prose around every bound number.** No gate reads the words a correctly
   bound number sits in. Read them against the ledger: the direction matches, the
   magnitude matches, a `candidate` is hedged, and a reader who reads only that sentence
   comes away with what the data supports. A `prose` finding.
5. **Test the boundary.** Every account the recipe's population rule could cover is in a
   check's population, ruled out with its basis, or an open item sized at its balance.
   Every member a check's coverage note excludes carries a route: a step, an `X.`, a `Q.`
   or a `D.`. An exclusion with no route is a `boundary` finding, graded by the member's
   balance.
6. **Test the empty results.** A population, class or list a check closed as empty is a
   `search` finding where the data room holds records that could have answered it. The
   defect is the search, not the absence.
7. **Judge the objective.** The run's goal is supported by what the checks establish, or
   it is not. Where it is not, the deliverable states which families ran, at what grain,
   over what coverage. A deliverable that reads as complete over a population no check
   tested is a blocking finding.
8. **Hold each check to its own procedure.** Resolve the check's kind to its worker skill
   through `KINDS` in `${CLAUDE_PLUGIN_ROOT}/scripts/check_playbook.py`, and read that
   skill's numbered sections — its procedure — with `section.py`. Stop there: `mode: fix`
   and `Record` are the worker's, not yours. A step the procedure requires and the record
   does not show is a `judgment` finding.

Where a deliverable has landed, its layout and its cells are held to
`${CLAUDE_PLUGIN_ROOT}/reference/WORKBOOK.md` and `WORKBOOK_STYLE.md`, and the deck to
`REPORT.md` § 3 and `REPORT.md` § 4. Read the section that governs the surface you are
judging.

## Findings

```yaml
- id: C.003
  check: boundary                  # the scope part it failed: prose | foot | reperform
                                   # | sample | boundary | search | judgment. `judgment`
                                   # quotes its DOCTRINE.md sentence in `rule`.
  severity: blocking | material | advisory
  target: {artifact: "checks/recon_cash.md", locator: "RI.unrecorded_fees"}
  observation: >-
    One or two sentences. What is wrong, not what should be done about it.
  rule: "An explanation is quantified against its own evidence, never the gap."
  fix_kind: rerun_check | data_request | management_question | review_call | withhold
  fix_check: recon_cash            # required when fix_kind is rerun_check
  fix_input: >-
    What the re-run must do differently. Concrete enough to act on.
  disposition: open | fixed | carried_to_open_items | withheld
  carried: true                    # only on a finding copied forward from carry_from
                                   # without re-performance, id and severity intact
  fix_attempted: true              # a fix round ran and the defect stands
```

### Severity

Grade by consequence to the reader.

- `blocking`: a number the reader could act on is wrong or unsupported. Does not ship.
- `material`: the reader's decision could change if they knew. Ships only as an open item
  or a stated limitation.
- `advisory`: register, ordering, phrasing. Fixed when cheap. Never `fix_kind:
  rerun_check`; route to `review_call`, and it is addressed when the check re-runs for a
  heavier finding.

A finding whose measured amount sits below a declared materiality is `advisory` unless it
points at a systematic defect, which is graded by its consequence (DOCTRINE.md
§ Materiality). A computation whose population a size threshold narrowed, e.g. accounts
left out of a breakdown or small items dropped from a footing, is `blocking` (DOCTRINE.md
§ Working with numbers).

### Routing

A finding gets one fix round (RUN_CONTRACT.md § Review and report). The fix re-run diffs
its new output against the old and records that the change is localized and the defect
corrected. That record closes the finding.

A defect a later review re-finds standing after its fix round keeps its id, gains
`fix_attempted: true`, and is re-routed: `blocking` to `withhold`, `material` or
`advisory` to `review_call`. The user rules on it. A blocking finding is never carried
into the deliverable as a footnote. It is fixed, or the figure is withheld.

### At termination

No finding ends `open`. Every one is `fixed`, `carried_to_open_items` or `withheld`, the
counts sum, and every carried item names its `from_finding`. Read the latest review
record together with the fix records that answered it: a finding the review left `open`
counts `fixed` when a later fix record carries its verified diff.
