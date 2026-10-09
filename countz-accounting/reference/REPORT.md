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

The deck's structure is the recipe's (`## Report`, RECIPE_FORMAT.md § Report), because
what a reader comes for differs by analysis: a quality of earnings review is read for its
EBITDA walk, so the walk leads; a revenue-leak diagnostic is read for its causes, risks
and actions, so its full bridge is support at the back. The parts, in this order:

**The opening.** Two pages, and at most one more:

1. **Executive summary** — headed exactly that. The elevator pitch: `message` is the one
   sentence an executive takes away, and it drives the rest of the deck — most of the
   pages after exist to support it. Under it, the stat tiles, chart or table that carry
   the message; never prose alone. Everything the recipe's `## Exec summary` says to lead
   with or to state beside the headline is on this page — a book error, an integrity
   pattern, a balance the records do not carry — each with its amount, never left to a
   late page alone. The page also holds:
   - **The order.** The message states the headline figure the recipe leads with, sized
     against the yardstick, and nothing else: an integrity matter is never joined to it in
     one sentence. The integrity matters come next, directly under the message, each on a
     line of its own with its amount; then a covenant, liquidity or going-concern
     consequence; then the balance arithmetic. A matter the recipe says to state beside the
     headline is never the last line of the page.
   - **What it means.** The consequence the workbook establishes, stated as a fact: a
     covenant the adjusted figure breaches, a prior period the adjustments reach, a draft
     note that states another figure. Where the workbook establishes none, say nothing.
   - **The yardstick and the corrected figure.** The headline effect beside materiality
     and the figure it changes as reported (pre-tax income, the balance), each a reference
     to its cell on Basis of Preparation or the check tab, and the sum stated: *pre-tax
     income of $1.4M as reported becomes $0.4M adjusted, and $0.2M if the pending
     adjustments hold*. Where the workbook holds neither, one sentence says so.
   - **The headline by nature.** From the walk's cause subtotals, how much of the net
     adjustment moves amounts between lines or periods (the boundary, presentation and
     classification causes, a timing difference that reverses after the period end), how
     much is non-cash, and how much misstates the total — on this page, in one sentence,
     with each part's amount. Where offsetting items each
     exceed the net, both directions with their amounts. Amounts of unlike kinds — loan
     principal and revenue, a balance and a flow — are never added into one figure.
   - **One meaning per figure.** Amounts on one page either add, or the page says which
     contains which: *the $257K of held invoices is part of the $1.5M unrecorded*. A list
     of pattern amounts carries, on the same page, the amount not already inside the
     headline — *all but the $140K warranty release is already in the $1.5M* — so no
     reader adds them. Pending adjustments are stated gross, each direction on its own,
     never netted into one figure.
   - **What "adjusted" means**, once, in plain words: the recorded figure after the
     adjustments the records support (the workbook's *as supported*). Where part of it
     rests on the company's own records alone, the share that does.
2. **The key metrics** — the executive summary continued as figures. Its headline names
   what it shows, the measure the report exists to state: the recipe's `## Report`
   declares it as `metrics.title` (`Adjusted EBITDA` for a quality of earnings review,
   `Days sales outstanding` for a revenue leak). Stat tiles, a chart or a short table per
   period; the recipe's prose says which figures.
3. **Matters for your attention**, where the run raised an integrity pattern: a party tied
   to an employee or officer, a payment with no book entry, a statement to a lender or a
   board the records contradict, a person approving or posting their own entries, tax
   withheld and not remitted. One page, headed exactly that, under the opening's kicker:
   each matter with its amount, what it may indicate in plain words (*a fictitious
   customer*, *receipts applied to conceal a shortfall*), and the role that receives it.
   A matter about a role's own records or conduct goes to a role independent of it — the
   audit committee or the board — never to that role. A matter goes on this page only where
   a record ties the pattern to the person or the money: a shared address, phone or bank
   account, an approval or a posting by the person, a document the records contradict, an
   amount paid or withheld. A resemblance alone — a shared surname, a similar name, a
   round amount — is a question on the page of what is open, not a matter here; so is a
   pattern the workbook rules benign or not related. Without such a pattern this page is
   optional and carries the story to the first `lead` schedule instead: a chart of the
   trend, a waterfall of the walk, the split that explains the headline.

**The lead schedules.** Each schedule the recipe places `lead`: the table a reader of
this report type opens it for — for a quality of earnings review, the EBITDA walk at item
grain and the roster of every adjustment considered with its verdict and reason. Each sits
in the recipe's order, directly after the opening.

**A schedule's length on the deck.** The deck is read by an executive; the workbook holds
every row. A schedule drops its nil rows (`nonzero: true`) — a cause with no adjustment, an
empty subtotal. One that still runs past 25 rows is condensed by its kind:
- **A walk** — a schedule with subtotals or derived lines (`= …`) — is shown at cause grain:
  `rows:` its opening line, each cause's subtotal and its closing line, which the builder
  holds to footing. A walk is never ranked with `largest`, and never shows some of a
  cause's items without the rest.
- **A flat list in one unit** (exceptions, items, accounts) shows the 25 rows carrying the
  largest amount (`largest: <amount column>`, `max_rows: 25`), and the builder states the
  count and amount of the rest. A column mixing money, days and ratios is not ranked; the
  list is split by measure or left to the workbook.

A recipe asking for a schedule "at full population" is held to this rule on the deck; its
tab carries the full population.

**The narrative.** The findings, what they rest on, what is open, what to do — pages
that refer to the schedules' rows by name and stat. Where the recipe declares
`narrative`, its sections in that order, each the kicker its pages carry. A table appears
once on the deck; a figure a narrative page needs is a reference, a stat tile or a chart,
never a schedule's rows again.

**The appendix.** A schedule the recipe places `appendix` goes on the deck where the
recipe marks it `required`, and otherwise only where the narrative cites rows of it a
reader needs to see; the workbook holds every appendix schedule. Where the recipe does not place it `lead`, the roster of every item considered,
with its verdict, reason and condition, is the reviewer's and stays in the workbook. A
schedule shown goes in the recipe's order,
after every narrative page, its pages carrying the kicker `Appendix`, under the length rule
above. Nothing but appendix pages follows the first of them.

**Lists on narrative pages.** A page listing findings, owners or open items shows at most
eight, ranked by the amount each can move in the reported figures — the walk line, the
pending adjustment or the exposure it settles — and states the count of the rest with the
tab that lists them. The Open Items tab's `Size` is a reference amount (a population, a
loan's principal), not an exposure: it never ranks a list or appears as one on the deck;
an item that moves no stated figure is listed without an amount. A recipe asking for
every `D.` and `Q.` item is held to this on the deck; the Open Items tab carries them all.

**Who answers.** On every page — the matters, the owners, the open items — a matter about a
role's own entries, approvals, pay or dealings is answered to a role independent of it:
the audit committee or the board receives it, and the role concerned supplies the records.
Never *the CFO answers* for the CFO's own entries.

**The records' date.** The page that states the scope says the date the records run to,
as a reference to its cell, and that events after it were not examined. A deck dated later
than the records states this once, on that page.

A run with no recipe has no schedules; its opening is the executive summary alone, and
the gate holds that page the same way.

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
4. **Read the built deck back** before the gate, as its reader would, slide by slide. List
   every item, count and total that appears on more than one page with the figure each
   page states; one item carries one figure from one cell everywhere (§ 3 One figure, one
   meaning), and an appendix total that differs from the headline is reconciled on its
   page. Fix `report.yaml` and rebuild until the list has no conflict.

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
operating legal entities · FY2023, as of September 30, 2023`), repeating neither the
company nor the title's words. The builder refuses a title carrying the period and a
subtitle repeating the title, and the gate refuses the period again on the sealed deck
(§ 5). That neither names the company is the critic's to hold (`check-review`): a
company's name, in any language and legal form, is a judgment, not a pattern.

**Headline and message.** A page's title is the headline, never the sentence. It names
the page's subject: `EBITDA`, `Working capital`, `Coverage`, `The money market holding`,
`Management's proposed adjustments`. A page carrying a table names what the table
covers. A ruling, a verdict or a reading of the rows is stated in `message`, in the first
person, beside the rows it rests on: `Acquired-intangible amortization rejected`, `Two
adjustments supported by the records`, `None of the twelve is supported` and `Every
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
| `table: {from, block?, rows?, columns?, where?, through?, max_rows?, nonzero?, largest?, title?, ids?, scale?, currency?, dense?}` | a table copied from a tab: its primary table, or the block under a heading (`Exceptions`, `Analysis`, a titled table on the Exec Summary). `rows` selects by leading label and `columns` by header. `where: {verdict: supported}` keeps the rows carrying a matching value in that column and every row with the column empty — a walk's mechanics, its subtotals — so a walk shows at item grain; `through: "= pro-forma EBITDA"` ends the table at that row, dropping the information lines under it. `max_rows` caps and states the rows left on the tab. `nonzero: true` drops a row nil in every money and count column shown, keeping every derived line. `largest: <header>` with `max_rows: N` keeps the N rows with the largest absolute amount in that column, in the tab's order, and states the count and amount of the rest; a recipe schedule is capped only this way (§ 1). `scale: units|thousands|millions|billions` states the money columns at that scale, written once in the table's title in their currency (§ 4); `currency: eur` names that currency where it is not the book's. `dense: true` sets the table at the dense size, for a schedule of many rows or columns. Ids are dropped unless `ids: true`. |
| `lines: {from, block, title?}` | a tab's statement block (Notes, To reperform, a How-to-read list) as bullets |
| `chart: {type, from, rows, columns?, block?, title?, labels?}` | `column`, `bar` or `line`, drawn on rows copied from a tab, at most four series; or `waterfall`, a walk drawn as floating bars — `rows` the walk's lines in order, the first and every derived line (`= …`) a total drawn from zero, every other line a step from the running total, and `columns` one period. Each bar carries its value. Where the steps are small beside the totals, the value axis starts above zero so the steps can be seen, the axis says so, and each total bar carries a break mark where the axis starts. `labels` gives the reader's words for each row, in order (`Reclassified to investments` for `Supported subtotal: boundary`); the figures stay the tab's. |
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
copied amounts. A table on the Exec Summary declares the tab it was copied from with the
marker `from: <tab>` in its title — the full tab name or its token (`EBITDA bridge · from:
q6`, `Walk (from: q6 EBITDA bridge)`) — and `link_workbook.py` links each amount in it to
its original there. The marker is the plugin's own syntax; a title is never read for a
word. Or `{tab!B3}`, one cell by coordinate. `tab` is the full tab name or the
token that opens it (`q6`, `r4 concentration`). A trailing `| $` marks a money figure in
the book's currency — the one the Exec Summary's basis line (B2) names, US dollars when it
names none (`{q6 | = Reported EBITDA | LTM Jul 2025 | $}` renders `$8.1M`; `€8.1M` in a
EUR book); `| $:eur` names another currency (`scripts/style.py` lists them). Without it a
number renders bare, so a count never carries a currency symbol. Prose figures follow
`DOCTRINE.md` § Number conventions. A reference to a text cell inserts the text. A
reference nothing resolves is a refusal naming it, never a blank.

A figure the workbook does not hold as one cell — the corrected result, *reported plus
the effect* — is computed from cells that it does: `{= [tab | row | column] + [tab | row |
column] - [tab | row | column] | $}`, each term in brackets a reference as above, joined by
`+` or `-`. The builder records each one with its terms beside the deck
(`report.computed.json`) and the gate admits it by them. Compute a sum or a difference of
figures the reader is shown, never a ratio or a figure the workbook does not imply.

**Fit.** The slide is 16:9. The body holds about 4.7 inches of stacked blocks under a
one-line headline, less under a two-line one or a message. A table or bullet list that
runs past the body continues onto the next page with `(continued)` in the headline, no
message, and the table header repeated. Any other block that measures past the body is
refused with the overflow named: split it or trim it. A continuation carries at least
three rows of a table or two items of a list, and a block that does not fit after a table
takes the table's last rows with it, so no page holds a note or a row alone. The builder
never shrinks a font: a
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
days after September 30, 2025, because the data room holds no general ledger past that
date"*, not *"the half of each window after the period end has no book side to test
against"*.

**Exceptions.** A result that raises no exception may stand on a total and a count: *"We
paired forty-three transfers moving $25.5m inside the window, every pair on one date and
therefore in one period."* An exception carries what the reader needs to find the item in
the records and reperform the test: the parties, the record's own identifier, the date and
amount on each side, and the effect at each period end the deck reports. Example: write
*"The US parent and its Australian subsidiary recorded the same intragroup settlement,
IC-SETTLE-APAC-2025-02, in different months. The parent recorded the receipt of $458K on
February 7, 2025 and the subsidiary recorded the payment on March 7, 2025, leaving the
intercompany accounts out of balance at February 28, 2025 by 1.2% of consolidated cash at
that month end. Both entries fall inside FY2025, so cash at September 30, 2025 is
unaffected."*, not *"One intragroup settlement posts its two legs a month apart, at $458K
a leg."*

**One figure, one meaning.** A measure the deck states on two pages is the same figure on
both; where the workbook carries it twice (`$296K` on the walk, `$312K` on the allowance
tab), the deck uses one and reconciles the other once, where it first appears. A sentence
or headline stating a total over listed parts lists parts that add to it, or says what the
rest is. A count in a headline equals the items under it. A direction word (*raise*,
*lower*, *overstated*) follows the tab's sign convention, stated on its row 2: read the sign
before writing the word. A ratio set against its threshold is stated at the precision that
shows which side of it the ratio falls (`1.16x against 1.25x`, never `1.2 against 1.2`).
A statement about a pattern carries the pattern's own facts (*four dates*, not *one day*;
*$283K open at the year end*, not *billed $455K and never paid* where part was re-billed or
written off).

**Run vocabulary.** State the basis only where the user chose it: *prepared on a buy-side
diligence basis, as instructed*. Where the recipe set that parameter by default, say nothing
about it. Where the recipe says the deliverable does not state a parameter, leave it out.

Do not print a parameter name (`perspective`, `maturity_basis`), `the user` for the client,
`this run` or `the run` for the report, `bucket` for a category, or a test's internal shorthand
(`direction`, `grain`) in place of what it tests. Nor the run's working words: *minted*,
*recipe*, *skill*, *rule 5*, *a hypothesis departed* or *held*, a step token (*E5 rules*,
*as U4 found*), a ledger id, a system user name where the role says it (*the controller*,
not *lnguyen*). The workbook's status words are replaced in the area's own terms (Working-paper
terms below).

A copied table arrives with the heading the tab gave it. Where that heading carries one of
these, select the block by the name the tab uses and set `title:` to what the slide shows.
The figures stay copied and the tab is untouched. Example: a tab heads a block `The bridge
with each of the five events of A0's register removed`, which names a check rather than the
schedule. The page selects that block and retitles it:

```yaml
- table:
    from: a5
    block: The bridge with each of the five events of A0's register removed
    title: Diligence ARR with each event removed
```

Where a copied CELL carries one of these, or any id `WORKBOOK.md` § 3 Language keeps off a
tab, the tab is wrong and the owning check fixes it: name the cell and the check, and end the
step `blocked`. Do not rewrite the tab, and do not drop the column to hide the cell.

**Workpaper terms.** The workbook's status words (*supported*, *candidate*,
*rejected*, a boundary *ruling*) and its names for its own mechanics stay in the workbook.
In what you write on a slide — a headline, a message, a text, a bullet, a note, a tile, a
chart's labels — say what happened to the item in the terms practitioners of that area use.
The term depends on the area and the item; no one substitute fits every deck. Examples:
*reclassified to restricted cash* (cash); *moved out of payroll cost to a loss* (payroll);
*not a related party, so outside the disclosure* (related parties); *not adjusted until the
lease is provided* (an item awaiting a record). Name a schedule what the area calls it (*the
bridge*, *the roll-forward*, *the reconciliation*), and write *adjusted* for as supported
(*adjusted cash*). The gate refuses *walk*, *as supported*, *candidate*, *boundary*,
*ruled* or *ruling*, *routed*, *standing*, *cause grain* and *review step* there. A copied
table's cells keep the tab's words, and the status note under it defines them, each in the
form `Candidate: …` (Status words below); a tab named in a sentence keeps its name.

Procedure stays in the workbook too. The deck states what was found and what it rests on,
and states a limit of the work as the amount it leaves untested and what that amount could
change: *we could not trace $1.6M of payments, so further unrecorded liabilities are
possible*. No page states the count of expectations or patterns tested, the count of files
read, performance materiality or a testing threshold; Basis of Preparation and Coverage
hold them. Materiality itself is the yardstick and stays (§ 1).

**Shares.** A percentage or ratio names the population it is a share of. Where a page
carries two populations, name both. Example: *a third of the past-due balance* beside
*no cause on $33.1m of the $50.5m rostered* is 33.9% of one population beside 65% of
another. A page showing a selection from a longer list names the list the same way: how
many items it holds, and what share of its amount the items shown carry.

**Status words.** A table carrying a verdict or a standing column (`supported`,
`candidate`, `rejected`, `underpowered`, `documented`, `indicative`) carries a `note`
under it that says what each word shown means, in one sentence each, in the reader's
words, the word first: *Indicative: inferred from payment behavior; the customer has not
confirmed the cause*. A reader outside accounting meets the word there, not in the workbook.

**Names.** A customer, vendor or counterparty is named as the tab names it (*Ramirez
Education Group*), with its record identifier beside the name only where the reader must
find it in the records. An identifier alone (*C1637*) tells an executive nothing.

**Actions.** A page of actions shows, per action, the owner, the cash and the days it
carries, and when it can start; it leads with the few actions that carry most of the
cash, states what share of the total they carry, and refers to the tab for the rest with
their count and amount.

Characterize evidence in the profession's terms. A bank statement is third-party
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

The deck is in the Countz deck system, which `build_report.py` holds: layout, type and
colors. Inter throughout. A sea-foam ground
(`F7F6F3`); ink (`1C2130`) for headlines and figures; secondary ink (`484C57`) for body
text; muted ink (`5E616A`) for labels, notes, footers and the message under a headline;
one teal (`0A5F6A`) as a 3 px rule above a block, on kickers and on chart series. Border
hairlines (`D8D8D9`) between table rows, no vertical rules or fills. In every table the first column reads left and every
other column reads right, header and body alike. The three semantic states appear on
status words only, as text. Negatives in parentheses; zero as an en dash in a table and
`$0` in a sentence. Every page ends in the teal band: the page's optional `tagline` on
the left in white, the confidential line with the page number and the source tabs on the
right, as `Source: workbook.xlsx / Cash walk · FX effect` — each tab by its name without the
roster token that opens it. All of it is the builder's; the author never styles.

**Numbers.** US conventions, from one table — `scripts/style.py` — that the builder writes
with and the gate reads back with. The builder applies these to every figure it
resolves; a figure typed into a sentence follows them too.

| | on the deck |
|---|---|
| a money figure in a sentence or a stat tile | scaled and rounded, with its currency: `$50.5M`, `$1.5M`, `$81K`, `$1.2B`, `$950` — `€8.4M`, `A$1.2M`, `CHF 81K` in another currency — not `$50,456,833` |
| days, ratios, multiples | one decimal at ten and above: `57.8 days`, not `57.78`; two below ten: `1.16x`, not `1.2x` |
| percentages | one decimal: `33.9%`; exact integers exactly: `100%` |
| a date | `Sep 30, 2025` in a table cell, `September 30, 2025` in a sentence and on the cover |
| a schedule of money copied from a tab | at the declared `scale:`, stated once in the table's title in its currency — `EBITDA bridge ($ in thousands)`; with money columns in more than one currency, `(in thousands)` and each column's currency in its header (`FY2025 (€)`) |
| a waterfall bar | as a stat tile states it: `$18.7M`; a step that is nil draws no bar |
| a count | never scaled: a column is a count by its format (the kit's `FMT_COUNT`, or a bare `#,##0`), never by its header's words |
| a total | a row the tab rules with the kit's double bottom rule (`Total`); a bold row without it is a subtotal, whatever its label says |

Text copied from the workbook (a cell referenced whole) keeps the
workbook's figures, stated to the unit. Where that clashes with the scale on the page,
write the message yourself and reference the figures.

## 5. The gate

`check_report.py` holds seven mechanical things and nothing about the story:

- **The figures.** Every number on a slide is backed by a workbook numeric cell within
  the rounding tolerance of the precision shown, a number stated in a workbook text cell,
  or a `workpapers/*.yaml` value (the admission `check_prose.py` makes), on its magnitude:
  a written sign is not checked. Money is read in every currency `scripts/style.py`
  defines. A table's scale is read from its title (`($ in thousands)`). A bare year is a
  period, not a figure.
- **The sources.** A page carrying a table, a chart or a stat names its tabs in the
  footer, each by its name without its roster token; every table on it comes from a tab
  named there.
- **The cover.** The title names the work and carries no period, within its length; the
  subtitle within its own (§ 2). Whether either names the company is the critic's.
- **The message.** Every title is a headline (at most 80 characters, no full stop), every
  `message` and `text` a complete sentence, and the deck has at least one page beyond the
  cover.
- **The schedules.** On a run whose recipe declares `## Report`, each schedule is on the
  deck as a table from its family's tab, carrying every declared column and period, at the
  population its `where` and `through` leave, less the rows nil in every period column
  shown: up to 25 rows, every row's identity is on the deck and none is trimmed; past
  25, a list shows its largest rows and states the rest, and a walk reaches its closing
  line at cause grain (§ 1). A schedule placed `appendix` is held to this where the recipe
  marks it `required` or the deck carries it. A period column is one naming a period the plan
  declares (`params.columns`, `scripts/periods.py`); `latest` is the latest by the plan's
  dates, else the last period column. A table on the deck showing two rows that read the
  same in every column shown is refused: the reader cannot tell them apart, so the
  owning check names each row distinctly.
- **The structure.** The first page after the cover is headed `Executive summary`,
  carries a `message` and at least one stat tile, table or chart. On a recipe run the
  second page is headed as the recipe's `metrics.title` and carries a figure block; the
  first `lead` schedule sits at most one page after it, and no narrative page stands
  between two `lead` schedules. Every page carrying an `appendix` schedule has the kicker
  `Appendix`, and every page after the first `Appendix` page has it too. Where the recipe
  declares `narrative`, every narrative page — after the opening and the lead schedules,
  before the appendix — carries one of its sections as its kicker, in the declared order.
- **The reader's words.** No ledger id (`Q.r4.ar_movement`, `LK.terms_not_enforced`) and no
  step token past a cell's opening (`as R4 measured it`, `(q1)`) on a page or in a table
  cell; and none of the working words § 3 lists (*minted*, *recipe*, *skill*, *rule 5*,
  *this run*, *the run*) anywhere on a slide, a copied table's cells included: a row carrying one
  stays off the deck. None of the working-paper terms § 3 lists in what the author writes on
  a slide; a term opening its definition and a tab's name are not read. The footers name
  tabs and are not read. A token shaped like a period (`Q1`) is
  read in lower case only. A copied row label carrying one is the owning check's to
  rewrite.

The author's pass is the brief (§ 1): the plan was written before the pages, the deck
tells the workbook's story to a reader outside accounting in the voice of `DOCTRINE.md`,
and the deck and the workbook read as one position.
