# RECIPE_FORMAT — what a playbook recipe document must contain

A playbook recipe declares which checks substantiate a fixed objective, over which source
classes, at what grain. This document is the contract two producers satisfy: the
**corpus** — the recipes authored in git under `playbook-recipes/`, listed in
`catalog.yaml` beside them, and served to a running plugin by the Countz connector
(`get_recipe_for_countz_analysis`), never shipped in the package — and a **generated
recipe**, which the `create-recipe` step writes on the user's machine for an analysis
the catalog does not cover. Either way a run reads its recipe from
`<run_dir>/recipes/<name>.md`, the bytes it pinned (`RUN_CONTRACT.md`).

A corpus recipe has exactly one shim skill (`context: inline`) that asks for it by its
`name` and points at `PLAYBOOK_RECIPES.md`; `cash` is the exemplar. A new corpus recipe
is the document, its `catalog.yaml` entry and its shim. A recipe composes check kinds
from `KINDS` in `scripts/check_playbook.py` and adds no orchestration. One module,
`scripts/recipe_format.py`, holds the shape rules below; `check-plugin.py` runs them over
the corpus and `scripts/validate_recipe.py` runs them over a generated recipe.

This file is read when a recipe is written. The rules a recipe's families run under, and
the procedure the relay follows, are `PLAYBOOK_RECIPES.md`.

## The document

A recipe is one markdown file: YAML frontmatter, then a body. The relay reads the
frontmatter before anything runs; the worker reads the body with its family.

The frontmatter:

```yaml
---
name: cash-substantiation      # the run's goal, and the drafted definition's name
objective: >-                  # what the run establishes; passed to the plan step verbatim
  establish, before an external audit begins, whether ...
declares:                      # optional: run-level options the user must state
  perspective: >-              # key -> the one-line choice the relay puts to the user
    buy_side | sell_side ...
headline: q6                   # optional: the one-check family whose walk is the
                               # deliverable's headline
                               # (PLAYBOOK_RECIPES.md § The headline walk)
lead: [q6, q5]                 # optional: the families whose tabs follow the Exec Summary,
                               # in reader order, headline first; absent, the headline
                               # family alone (WORKBOOK.md § 2)
---
```

`name` and `objective` are required. No other key is accepted.

A `declares` key is an option the relay collects with the sources and passes to the plan
verbatim as `declared`; the recipe's body says which steps' `params` carry it. Where the
user does not choose, the option's line carries the answer to use and the plan states
which it took. A line that says *no default* is asked again (`RUN_CONTRACT.md`
§ Parameters).

`headline` names a family whose section declares one check. `check-report` finds that
check in `run.json.checks` by `params.family` and builds the Exec Summary on its walk.

`lead` names the families whose tabs sit directly after the Exec Summary, the headline
family first. `check-report` orders the workbook by it; absent, by the headline family
alone (WORKBOOK.md § 2).

### The body

Seven sections are required, in this order: `Population`, `Source classes`,
`Granularity`, `The families`, `Exec summary`, `Report`, `What the plan notes rather
than checks`. Other sections may sit between them. Each is described below with the rule
it inherits; the recipe writes its own content under the heading and restates no
inherited rule under a heading of its own.

#### `Population`

The closed list the run's population is ruled from, drawn top-down from the objective —
the statement line, the trial-balance accounts that compose it, the general-ledger
accounts behind each — never from which account names read as in scope. The section
carries the definition the population family rules against and the accounts outside the
line it reaches as candidates (DOCTRINE.md § Populations). Where the population family's
ruling differs from the plan's, its record states the divergence and the relay puts it to
the user (§ 3).

#### `Source classes`

The records the recipe expects in each class, and the class its objective rests on. The
three classes and the standing each carries are `PLAYBOOK_RECIPES.md` § The source-class
ladder; this section names the records, not the ladder.

#### `Granularity`

The grain each family runs at and the floor below which the recipe does not go. Every
family runs at the finest grain its data carries; the plan states each family's grain with
the data fact that sets it. An unstated coarsening is a review finding.

#### `The families`

One `###` per family, headed exactly
`### <F><n> — <title> (kind \`<kind>\`, <cardinality>)`. Example: `### C4 — the books meet
the bank (kind \`recon\`, per bank account)`. `<F>` is one upper-case letter, `<n>` one
digit, `<kind>` a key of `KINDS`. Number from 0 where family 0 is the population walk,
from 1 otherwise. Each family states what it establishes, what it reads from the data
room, and what it reads from other families — the reads the plan carries as `_from`
params. A family never states an order: the plan derives each step's `after` from its
reads (`PLAYBOOKS.md` § The file), because the order depends on the data room the
recipe cannot see. `validate_recipe.py` refuses `after ...` in a family header.

`<cardinality>` states the grain the family's procedure runs at — `per bank account`, `per
fiscal year`, `one check`, `one check across accounts` — and never how many checks perform
it. `per <entity>` is one assertion set per entity, which the plan carries in one step
unless a measured fact splits it (`PLAYBOOK_RECIPES.md` § How a family becomes steps); a
recipe that wants a family kept to one entity per step says so in the family's body, with
the reason. `headline` names a family whose cardinality reads `one check`.

#### `Exec summary`

Who the deliverable's first tab is for, what they came to learn and what the story leads
with. `check-report` writes that tab and the deck's executive summary from it
(WORKBOOK.md § 6, REPORT.md § 2).

#### Report

The deck's opening and the schedules it carries before its narrative pages (REPORT.md
§ 1). Prose first — what the key-metrics page shows, what each schedule shows and why the
narrative refers to it rather than copying it — then exactly one fenced ```` ```json ````
block, `{"metrics": {...}, "schedules": [...]}`, with no other key.

`metrics` is one mapping, `{"title": ...}`: the headline of the key-metrics page, the
second page of the deck, naming the measure the report exists to state (`Adjusted
EBITDA`, `Cash as substantiated`). `check_report.py` refuses a deck whose second page is
headed otherwise. `schedules` is a non-empty list, one mapping per schedule:

| key | |
|---|---|
| `title` | the page headline |
| `from` | the family whose tab holds it (`q6`); the deck's table comes from that tab |
| `columns` | header words the table must carry; the first is the row's identity, the word the gate matches rows on (`name`, `account`) |
| `block` | optional; a titled block on the tab; the primary table otherwise |
| `where` | optional; `{"verdict": "supported"}` or a list of values — a row carrying a value in that column stays when it matches; a row with the column empty stays regardless |
| `through` | optional; the label of the row the schedule ends at, inclusive |
| `periods` | optional; `all` — every period column of the tab; `latest` — the latest by date; `none`. A period column is one naming a period the plan declares (`params.columns`) |
| `scale` | optional; `units`, `thousands`, `millions` or `billions` — stated once in the table's title in the money columns' currency (`EBITDA bridge ($ in thousands)`), never in each column header |
| `currency` | optional; a lower-case ISO 4217 code `scripts/style.py` defines (`eur`); the book's currency otherwise |
| `dense` | optional; `true` sets the table at the dense size (REPORT.md § 2) |
| `ids` | optional; `true` keeps the id column |

`check-report` builds each schedule as one `table:` block with the same keys, in the
recipe's order, directly after the opening; `check_report.py` refuses a deck on which a
schedule is absent, lacks a declared column or period, or shows fewer rows than the tab
holds under its `where` and `through` (REPORT.md § 5). `validate_recipe.py` refuses a
block that does not parse, a missing or empty `metrics.title`, a schedule missing
`title`, `from` or `columns`, a `from` naming no family, and an unknown key.

#### `What the plan notes rather than checks`

What the objective touches and the run does not test: each routed to the report's open
items with the plan's citation that surfaced it, and what puts it out of the run's reach.

#### Sections a recipe adds

Whatever the diagnostic needs, between the required sections. The live recipes carry `The
adjustment record`, `The expectation register`, `Data quality`, `Perspective`, and the
frames their walks rule against. `The period set` is where a recipe narrows DOCTRINE.md
§ Periods to the columns its objective carries.
