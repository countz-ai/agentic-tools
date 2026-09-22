# REPORT — the report deck

`WORKBOOK.md` is the reviewer's and the reperformer's surface. This file is the
decider's: `out/report.pptx`, the report the firm presents to the client. It states what
the author of the deck is given, the deck's source document, and what the builder and the
gate hold. What the deck contains is the author's decision, taken from the whole workbook.

## 1. The brief

You are a partner at the firm presenting the results in `workbook.xlsx` to the client.
The deck gets the message across to client executives who are not accountants (§ 3).
Charts where they help the message, plain and self-explanatory, never decorative.

The reader is the company's own executives and operators (the CFO, the controller, the
process owner) unless the run declares a transaction reader (`RUN_CONTRACT.md`
§ Parameters). Do not infer a transaction from the data room's name or its files. With no
declaration the deck closes on what the company does about what was found.

The deck is three parts, in this order.

**The opening.** Two pages, and at most one more:

1. **Executive summary** — headed exactly that. The elevator pitch: `message` is the one
   sentence an executive takes away, and it drives the rest of the deck — most of the
   pages after exist to support it. Under it, the stat tiles, chart or table that carry
   the message; never prose alone.
2. **The key metrics** — the executive summary continued as figures. Its headline names
   what it shows, the measure the report exists to state: the recipe's `## Report`
   declares it as `metrics.title` (`Adjusted EBITDA` for a quality of earnings review,
   `Days sales outstanding` for a revenue leak). Stat tiles, a chart or a short table per
   period; the recipe's prose says which figures.
3. Optionally one page that carries the story to the first schedule — a chart of the
   trend, the split that explains the headline — where the schedule needs it.

**The schedules.** The recipe's `## Report` declares the tables a reader of this report
type opens it for (RECIPE_FORMAT.md § Report) — for a quality of earnings review, the
EBITDA walk at item grain and the roster of every adjustment considered with its verdict
and reason. Each is one page, continued over as many as it takes, at full population, in
the recipe's order, directly after the opening. A run with no recipe has no schedules
part; its opening is the executive summary alone, and the gate holds that page the same
way.

**The narrative.** The findings, what they rest on, what is open — pages that refer to
the schedules' rows by name and stat, and copy no schedule a second time. A table
appears once on the deck; a figure a narrative page needs is a reference or a stat tile,
never the schedule's rows again.

Three rules:

1. **Use the real data from the workbook, and invent none.** Every figure on a slide is a
   reference to a workbook cell or a table copied from a tab (§ 2). The builder resolves
   them and the gate refuses a number no cell backs (§ 5). The material is the whole
   workbook: every check tab, Basis of Preparation, Coverage, Open Items.
2. **Plan first.** Read the whole workbook. Decide the story, which pages tell it, each
   page's one message and the tabs it draws on. Write the plan down before writing a
   page. Pages go where the findings and the reader's decisions are.
3. **Generate the pages to the plan**, one message per page, and build the deck with the
   script.

## 2. `report.yaml` — the document

Written to `out/.staging/report.yaml` beside the workbook, kept at `out/report.yaml`
after the seal so a re-assembly edits it. The builder adds the cover, the footers and the
page numbers; the author writes everything else. There is no contents page and no
section divider; a section is the kicker its pages carry.

```yaml
schema: countz-accounting/report@1
title: ...                               # the playbook's report title; the recipe's goal in words otherwise
company: ...                             # default run.json inputs.company
subtitle: ...                            # default Exec Summary!B2 with the company mention dropped, cut to the whole `·` segments that fit the cover
date: ...                                # default today

sections:
  - title: ...                           # a section: the kicker its pages carry
    pages:
      - title: ...                       # the headline; at most 80 characters, two lines, no full stop
        message: ...                     # optional; the page's message as one complete sentence, under the headline
        kicker: ...                      # optional; default the section title
        tagline: ...                     # optional; the page's takeaway, in the footer band
        blocks: [...]
        source: [...]                    # optional; tabs a table or reference touches are added
```

**The cover.** Four strings, each fact on it once: the company as the kicker, the
`title`, the `subtitle`, and `Prepared for <company> by Countz · <date>`. `title` names
the work and nothing else (`Quality of earnings review`, `Revenue leak: billed to
collected`): no company, no period or as-of date, at most 60 characters. `subtitle`
carries the entity detail and the period on one line, at most 72 characters (`Seventeen
operating legal entities · FY2023, as of 30 September 2023`), repeating neither the
company nor the title's words. The builder refuses both, and the gate refuses them again
on the sealed deck (§ 5).

**Headline and message.** A page's title is the headline, never the sentence. It names
the page's subject: `EBITDA`, `Working capital`, `Coverage`, `The money market holding`,
`Management's proposed adjustments`. A page carrying a table names what the table
covers. A ruling, a verdict or a reading of the rows is stated in `message`, in the first
person, beside the rows it rests on: `Acquired-intangible amortisation rejected`, `Two
adjustments carried at supported standing`, `None of the twelve is supported` and `Every
account fails` are messages, and none of them is a title. A title carries no verb in the
passive and no participle standing for one (`ruled`, `carried`, `rejected`). Do not open a title on `no`, `none`, `not`, `never`, `every`, `all`,
`neither` or `nothing`.

The sentence that states the message in full goes in `message`, under the headline, and
only where the page needs it, in the voice of `DOCTRINE.md` § Voice. Example: `We
measured diligence-adjusted EBITDA at $8,404,000 for LTM Jul 2025, $1,246,000 below
management's figure, after we cut or rejected three of six addbacks.` A page whose stats
and table are all about the one subject named in its headline needs none; a page whose
point is one ruling always does. Decide page by page, from
the blocks. A headline or a message that states a count agrees with the number of items
under it.

**Prose.** Every sentence on a slide (a `message`, a `text` block) is complete and plain:
opens with a capital, ends with a full stop, and says one thing a reader outside
accounting follows on first reading. The builder refuses a fragment and a clipped
sentence (`…`); it never trims one.

**Blocks**, one key each; every string may carry references:

| block | carries |
|---|---|
| `text: "..."` | a paragraph; `lead: true` sets it larger |
| `heading: "..."` | a sub-heading inside the page |
| `note: "..."` | a small italic line |
| `bullets: [...]` | a list |
| `stats: [{label, value, note?}]` | up to four figure tiles across the page |
| `kv: [{label, value}]` | label and value pairs |
| `table: {from, block?, rows?, columns?, where?, through?, max_rows?, title?, ids?, scale?, dense?}` | a table copied from a tab: its primary table, or the block under a heading (`Exceptions`, `Analysis`, a titled table on the Exec Summary). `rows` selects by leading label and `columns` by header. `where: {verdict: supported}` keeps the rows carrying a matching value in that column and every row with the column empty — a walk's mechanics, its subtotals — so a walk shows at item grain; `through: "= pro-forma EBITDA"` ends the table at that row, dropping the information lines under it. `max_rows` caps and states the rows left on the tab; a recipe schedule is never capped. `scale: thousands|millions` states the dollar columns at that scale and heads them with it (§ 4). `dense: true` sets the table at the dense size, for a schedule shown at full population. Ids are dropped unless `ids: true`. |
| `lines: {from, block, title?}` | a tab's statement block (Notes, To reperform, a How-to-read list) as bullets |
| `chart: {type, from, rows, columns?, block?, title?}` | `column`, `bar` or `line`, drawn on rows copied from a tab, at most four series |
| `columns: {widths, items}` | two or three lists of blocks side by side; `widths` sum to 1 |

**Condensed schedules.** A derived line (`= …`) shown above contributing lines equals the
derived line before it plus the lines shown between them. Copy the tab's run of rows
whole, or select rows that foot. The builder refuses a derived line the rows shown do not
make, and names the rows dropped. Two derived lines with nothing shown between them state
no arithmetic. A subtotal shown beside the rows it sums is not added a second time: where
body rows and subtotal rows both stand between two derived lines, the body rows are the
terms.

**What is open.** A page that closes on what the run could not settle is built from the
Open Items tab, not written from memory of it. Every item shown carries its size and the
function that answers it, and states the position first, then what is asked for, then
what the answer decides. Example, one item stated well and badly:

- *"The customer master names a payer for each customer. On the accounts behind $39.9m it
  names one of two parties, `P-payer_01` and `P-cardproc_01`, and neither has a customer
  record, so neither carries payment terms or an addressee. What each one is, and which
  party it settles for, decides whether the concentration on page 9 is one counterparty or
  350. $39.9m · credit and cash application"*
- Not: *"The identity of the two payer identifiers: whether each is the obligor or a
  settlement intermediary, and what terms attach to it."*

**References.** A number in prose is `{tab | row label | column header}`: the cell where
the row whose leading text is the label meets the column with that header, both copied
verbatim from the tab, the same match `link_workbook.py` makes for the Exec Summary's
copied amounts. Or `{tab!B3}`, one cell by coordinate. `tab` is the full tab name or the
token that opens it (`q6`, `r4 concentration`). A trailing `| $` marks a dollar figure
(`{q6 | = Reported EBITDA | LTM Jul 2025 | $}` renders `$8,070,000`); without it a
number renders bare, so a count never carries a currency symbol. Prose figures follow
`DOCTRINE.md` § Number conventions. A reference to a text cell inserts the text. A
reference nothing resolves is a refusal naming it, never a blank.

**Fit.** The slide is 16:9. The body holds about 4.7 inches of stacked blocks under a
one-line headline, less under a two-line one or a message. A table or bullet list that
runs past the body continues onto the next page with `(continued)` in the headline, no
message, and the table header repeated. Any other block that measures past the body is
refused with the overflow named: split it or trim it. The builder never shrinks a font: a
table is set at 10.5pt, at 9.75pt past six columns or fourteen rows, and at 8.25pt only
where the author declares `dense: true`.

Build and gate, from the run directory:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_report.py <run_dir>
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_report.py <run_dir>/out/.staging/report.pptx --run-dir <run_dir>
```

## 3. Tone

Voice is `DOCTRINE.md` § Voice: procedures in the first person plural, past tense, active;
no sentence whose point is a distinction. Every example in this file follows it; imitate
the examples, not this file's own instruction prose. The deck is an advisory report to a
client executive, in standard advisory vocabulary throughout: *the bridge*, *adjusted
EBITDA*, *reconciliation*, *unreconciled difference*, *exception*, *finding*,
*management represents*, *we were unable to obtain*, *recommendation*. The workbook's working-paper
terms (`WORKBOOK.md` § 3) carry over unchanged where the deck states the same thing. The
run's machine vocabulary does not carry over. A tab states a status in the reader's own
words and the deck copies it verbatim: *unable to establish*, never `withheld`;
*difference*, never `break`. A working-paper term belonging to another discipline does not
carry over either: *the corresponding entry*, never *the leg*.

**Measure names.** Call a measure what the workbook calls it: *best-possible days sales
outstanding*, *average days delinquent*, *adjusted EBITDA*. Do not substitute a plainer
word. Example: write *"Days sales outstanding is 57.8 days against a best-possible
34.6"*, not *"against a floor of 34.6"*.

**First mention.** An object the deck states a finding or a question about is defined
where it first appears: the record it comes from, how many there are, what they are
called, and the amount behind it. It carries that name on every page after; a later page
refers back and never re-introduces. A term of art inside a question the reader is asked
to answer is glossed where it is used: *the obligor, the party that owes the debt*.

**Referents.** A reader who opens the deck at one page understands every sentence on it
without reading another page and without knowing how the run works. A sentence resting on
one of the run's own nouns says what that noun is: *the window*, *the direction*, *the
book side*, *the population*, *the walk*. A page's `message` renders above the blocks
under it and defines what it uses. Example: write *"we could not test the five business
days after 30 September 2025, because the data room holds no general ledger past that
date"*, not *"the half of each window after the period end has no book side to test
against"*.

**Exceptions.** A result that raises no exception may stand on a total and a count: *"We
paired forty-three transfers moving $25.5m inside the window, every pair on one date and
therefore in one period."* An exception carries what the reader needs to find the item in
the records and reperform the test: the parties, the record's own identifier, the date and
amount on each side, and the effect at each period end the deck reports. Example: write
*"The US parent and its Australian subsidiary recorded the same intragroup settlement,
IC-SETTLE-APAC-2025-02, in different months. The parent recorded the receipt of $458k on
7 February 2025 and the subsidiary recorded the payment on 7 March 2025, leaving the
intercompany accounts out of balance at 28 February 2025 by 1.2% of consolidated cash at
that month end. Both entries fall inside FY2025, so cash at 30 September 2025 is
unaffected."*, not *"One intragroup settlement posts its two legs a month apart, at $458k
a leg."*

**Run vocabulary.** State the basis in words: *prepared on a buy-side diligence basis, as
instructed*. Do not print a parameter name (`leak_stance`, `maturity_basis`), `the user`
for the client, `this run` for the report, `bucket` for a category, or a test's internal
shorthand (`direction`, `grain`) in place of what it tests. Where a copied tab
title carries one, retitle the table with `title:`; the figures stay copied.

**Shares.** A percentage or ratio names the population it is a share of. Where a page
carries two populations, name both. Example: *a third of the past-due balance* beside
*no cause on $33.1m of the $50.5m rostered* is 33.9% of one population beside 65% of
another. A page showing a selection from a longer list names the list the same way: how
many items it holds, and what share of its amount the items shown carry.

Characterise evidence in the profession's terms. A bank statement is third-party
evidence, so an unreconciled account is *unreconciled*, never *taken on the bank's word*.

Example, the same page message stated well and badly:

- *"We reconciled ledger cash to the banks' stated balances with no unexplained
  difference, but only in aggregate: we could not reconcile seven of the thirteen
  accounts, because the ledger carries no balance per account."*
- Not: *"The books meet the thirteen institutions with nothing unexplained, but the tie
  holds only in aggregate and seven accounts stand on the institutions' word alone."*
  Coined terms, agentless verbs, and a sentence built to land a contrast.
- Not: *"Ledger cash reconciles to the banks' stated balances with no unexplained
  difference, but only in aggregate: seven accounts carry no reconciliation."* Standard
  terms, but the procedure has no one performing it.

## 4. Style

The deck is in the Countz deck system, held in px by `scripts/design/slide_layout.py` in
the monorepo and mirrored in inches and points by `build_report.py`. Inter throughout. A
bone ground (`F5F3EE`); ink for headlines and figures; a dark-grey body text; a muted
grey for labels, notes, footers and the message under a headline; one teal accent as a
3 px rule above a block, on kickers and on chart series. Bone hairlines between table
rows, no vertical rules or fills. In every table the first column reads left and every
other column reads right, header and body alike. The three semantic states appear on
status words only, as text. Negatives in parentheses; zero as an en dash in a table and
`$0` in a sentence. Every page ends in the teal band: the page's optional `tagline` on
the left in white, the confidential line with the page number and the source tabs on the
right. All of it is the builder's; the author never styles.

**Numbers.** The builder applies these to every figure it resolves; a figure typed into a
sentence follows them too.

| | on the deck |
|---|---|
| a dollar figure in a sentence or a stat tile | scaled and rounded: `$50.5m`, `$1.5m`, `$81k`, `$950`, not `$50,456,833` |
| days, ratios, multiples | one decimal: `57.8 days`, not `57.78` |
| percentages | one decimal: `33.9%`; exact integers exactly: `100%` |
| a schedule of dollars copied from a tab | at the scale you declare, `scale: thousands` or `millions`: each dollar column is headed `($'000)` and reads `64,143`, and the schedule foots at that scale |

Text copied from the workbook (a cell referenced whole) keeps the
workbook's figures, stated to the dollar. Where that clashes with the scale on the page,
write the message yourself and reference the figures.

## 5. The gate

`check_report.py` holds six mechanical things and nothing about the story:

- **The figures.** Every number on a slide is backed by a workbook numeric cell within
  the rounding tolerance of the precision shown, a number stated in a workbook text cell,
  or a `workpapers/*.yaml` value (the admission `check_prose.py` makes).
- **The sources.** A page carrying a table, a chart or a stat names its tabs in the
  footer; every table on it comes from a tab named there.
- **The cover.** The title names the work, carrying neither the company nor the period,
  and the subtitle carries the entity and the period without repeating the company (§ 2).
- **The message.** Every title is a headline (at most 80 characters, no full stop), every
  `message` and `text` a complete sentence, and the deck has at least one page beyond the
  cover.
- **The schedules.** On a run whose recipe declares `## Report`, each schedule is on the
  deck as a table from its family's tab, carrying every declared column and period, at the
  full population its `where` and `through` leave: every row's identity is on the deck,
  and none is trimmed to `max_rows`.
- **The opening.** The first page after the cover is headed `Executive summary`, carries a
  `message` and at least one stat tile, table or chart. On a recipe run the second page is
  headed as the recipe's `metrics.title` and carries a figure block, and the first
  schedule sits at most one page after it.

The author's pass is the brief (§ 1): the plan was written before the pages, the deck
tells the workbook's story to a reader outside accounting in the voice of `DOCTRINE.md`,
and the deck and the workbook read as one position.
