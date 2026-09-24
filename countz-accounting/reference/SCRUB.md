# SCRUB — the one text that crosses to the Countz connector

Nothing from a run goes to the server, with one exception (`OBSERVABILITY.md § 4`): on a
catalog miss, `countz-analysis` sends a **description of the analysis** the user asked
for, so the server can match it once more or plan a recipe for it. This document states
what that description may carry. The `scrubber` agent (`agents/scrubber.md`) applies it.

Whether a word identifies a company is a question about meaning, so a reader decides it,
not a pattern. The procedure — scrub, blind check, record, tell then send — is
`skills/countz-analysis/SKILL.md` step 4.

## What the description keeps

- **The analysis being asked for**, in accounting terms: what is tested, reconciled,
  measured or rolled forward, over what kind of population, at what grain.
- **Accounting standards and frameworks**: ASC 606, ASC 842, IFRS 16, GAAP, SOX.
- **Generic descriptions of the business**: "a SaaS company", "a multi-entity retailer",
  "a distributor with foreign subsidiaries" — a class of company, never one company.
- **Generic kinds of record**: "the general ledger", "bank statements", "the AR aging",
  "a lease register", "the contract listing".
- **Period vocabulary**: `FY2025`, `Q3 2025`, `March 2026`, "the last twelve months",
  "year end", "month end".

## What the description never carries

| Class (`category` in the record) | Rewrite as |
|---|---|
| `company_name` — incl. parent, subsidiaries, trade names, tickers | "the company", "a subsidiary" |
| `counterparty_name` | "a customer", "the bank" |
| `person_name` | "the controller", "management" |
| `product_name` | "a subscription product" |
| `figure` — in digits or in words | "a materiality threshold", "a large balance" |
| `identifier` — account, invoice, contract, entity numbers, any code | "the cash accounts", "the invoices" |
| `file_reference` — file, sheet, path, URL, email address | "the ledger export" |
| `location` | "a foreign subsidiary" (country only where it names the accounting regime, e.g. "a UK entity") |
| `system_name` | "the billing system" (a widely used product's category, never a custom name) |
| `date` — finer than the period vocabulary | "month end", "Q3 2025" |
| `quotation` — text copied from a source, email or note | a paraphrase in generic terms |
| `other` — anything that would let a reader who knows the market guess the company | the generic class it belongs to |

When in doubt, remove it. A description that is too generic costs a less specific recipe;
a description that identifies the company cannot be taken back once sent.
