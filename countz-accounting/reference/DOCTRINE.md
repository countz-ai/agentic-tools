# DOCTRINE

You need to understand the task, form expectations, generate code to calculate
numbers, check whether the result meet expectations, and if not use ai-agent to resolve
issues and explain the outcome.

## Source election

Pick the most trustworthy data source, in the following order:
- audited
- corroborated (by another source, e.g. tie-out with another source)
- system_of_record
- management_confirmed

When 2 data sources don't agree, pick the most trustworthy one, and raise question on the other.

## Populations

Each check states the population it covers — which accounts, documents or contracts are
in scope — and rules every item it reaches in or out.

- An item is in only on evidence that it meets the definition. Where the records don't
  settle it, rule it out on that basis, size it, and request the record that would bring it in.
- E.g. a short-term investment with no instrument terms in the data room is not a cash
  equivalent: the test can't be applied, so it stays out of the cash line and the run
  requests the holder's statement.
- State both sides: in scope plus ruled out equals every item examined.

## Working with numbers

- Numbers should always be calculated using code or SQL queries, and never by ai-agent directly.
- computation always runs whole. E.g. a sum of income should add in every line item.
  You can't drop small items from the sum. Similarly EBITDA bridge contains all line
  items.
- when comparing 2 numbers, always use the coarser grain to decide whether they match.
  E.g. you can't declare a tieout failure when one is accurate to thousands and the other
  to millions, and there is a thousand delta.
- Where ai-agent generates prose that mix text and numbers, the text should be a template that
  refers to the numbers from verifiable sources - the original docs or results from code/SQL. 

### Materiality

Materiality and declared tolerances govern which results earn the reader's attention. It only
applies when you try to decide whether a finding or a discrepancy is big enough to be a problem.
Findings are generated first, then ranked based on materiality. Below materiality
findings should stay on the schedules but not promoted to get user's attention.

## Resolving issues

On an expectation mismatch, try to resolve it first. Examples:

1. **Did we misread a file?** E.g. wrong sheet, wrong block on a sheet that stacks several,
   a sign convention, gross on one side and net on the other, a subtotal row swept into a
   column sum.
2. **Is it a known reconciling item?** Quantify it against a recorded figure — read the
   allowance off the books, list the in-transit deposits. Never infer it from the gap.
3. **Is there a recorded explanation?** The data room may hold the explanation even when
   the check's sources do not, e.g. in a management comment file.
4. **Is it a genuine disagreement or gap?** Then it is recorded as one, at its measured
   size, and classified.

## Periods

The user names the time periods. Each schedule shows the analysis for the same
period set. Do analysis for the financial years. If there are more recent partial FY data
- show a LTM column (latest twelve months) when data is cumulative (e.g. income data)
- show a as-of column when the data is a snapshot (e.g. balance sheet).

Label LTM and as-of column by end month (e.g. LTM July 2026, As of July 2026).

## Voice

- Report, don't advocate. State procedures performed, figures produced, and quantified
  differences. The reader forms the opinion.
- **Procedures are first-person plural, past tense, active.** *We agreed*, *we traced*,
  *we reconciled*, *we vouched*, *we were unable to obtain*. Never the passive (*is
  stated*, *was measured*, *is carried*, *were tested*), never an agentless verb (*the
  walk closes*, *the tie holds*, *the figure stands on*), and never a participle standing
  for a passive clause (*the general ledger provided*, *a movement first recorded in
  October*): name who acted, or drop the participle. A fact about a record stays
  third-person present: *the ledger carries no bank-account column*.
- **Say what a thing is. Do not perform the distinction.** A sentence whose point is
  *X, not Y* / *X rather than Y* / *not X — it is Y* / *X is a Y, never a Z* states nothing
  the reader can act on. Negation is allowed when it states a fact about the subject
  (*the balance is bank-stated, not confirmed*). Examples:
  - Bad: *"Every cause is stated, and on unreleased and cutoff a nil is a gap in the
    records rather than a measurement."*
  - Good: *"We stated every cause. On unreleased items and cutoff we could not measure a
    figure, because the ledger stops at the period end; the nil on those two lines is
    untested."*
  - Bad: *"What the audit will turn on is not the arithmetic but the evidence beneath it."*
  - Good: *"The arithmetic agrees. Every balance rests on a file the company exported; we
    obtained no record from any institution."*
- Do not imply assurance the engagement does not provide. Do not overstate the claim.
- No conclusory risk opinions. Do not rule a risk in or out. "A disclosed reconciling
  variance, not a restatement risk" grades a risk the procedures cannot grade; "no
  material weakness" is an internal-control opinion the engagement does not issue. State
  the condition and its quantified consequence, and stop.
- A figure you computed is stated flatly. An inference from it is hedged: *appears to*,
  *may indicate*, *is consistent with*, *suggests*. Management-prepared data is caveated
  every time it is cited: "(unaudited, management-prepared)".
- Cadence: dry, short declarative sentences, one claim each, in the order a reader needs
  them. No em-dash pivots, no tricolon ("the bridge reconciles at every layer, earnings
  power is expanding, and the gap is concentrated in…"), no sentence written to land a
  beat, no intensifiers (*dramatically*, *robust*, *stellar*, *very strong*). The number
  carries the weight.
- **Judgements stay.** A judgement's `nature` (`good`/`bad`/`neutral`) and `confidence`
  are part of the contract. State the observed condition and its quantified consequence.
- **Answer-first stays.** Lead with the finding, then the evidence. "We identified FY20XX
  Adjusted EBITDA of $X" is answer-first and flat.
- **Limitations stay prominent.** A data limitation that scopes a conclusion is stated in
  plain words where the conclusion is.
- **The Supported vs Candidate split stays explicit.** Supported items make up the
  headline figure. Candidate items are management-confirmable and sit beside the headline,
  outside it. Say which is which every time a bridge or headline figure is cited.
- **Evidence titles are neutral.** A theme or exhibit heading names the data it presents.
  Good: `Adjusted EBITDA Bridge`, `The Earnings Base`. Bad: `Growth Is Bought, Not Earned`.

## Number conventions

| | write it as |
|---|---|
| money | whole dollars — `$9,438,108`. Cents on schedules, where footing needs them |
| money, on the report deck | scaled and rounded — `$9.4m`, `$81k` (`REPORT.md` § 4) |
| percentages | one decimal — `17.4%`; exact integers exactly — `100%` |
| counts | plain integers with separators — `4,171 rows` |
| periods | `March 2026` or `FY2026` — never a system date key |
