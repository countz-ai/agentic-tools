---
name: create-recipe
description: >-
  Author a goal-based playbook recipe for an analysis the catalog does not cover,
  grounded in how practicing accountants perform and report the analysis. In a run: a
  draft stage that reads the registered data room and returns the questions the recipe
  needs answered, then an author stage that writes the recipe to the run directory and
  validates it against the recipe contract.
context: fork
agent: countz-accounting:planner
background: false
user-invocable: false
---

# Author a recipe

§ What a recipe states, § Research and § Write the recipe apply to every recipe: one
generated in a run, and one written for the corpus outside a run. § In a run applies to
the run's `create-recipe` step only.

Read `${CLAUDE_PLUGIN_ROOT}/reference/RECIPE_FORMAT.md` whole; it is the contract you
write to. Then read
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "What every recipe inherits"`
and `${CLAUDE_PLUGIN_ROOT}/reference/DOCTRINE.md` § Voice and § Number conventions.

## What a recipe states

A recipe is a contract. It states what the run must establish and how a reviewer judges
it. The planner and the workers choose the method. Four things decide its content:

1. The problem space: the decision the analysis serves, who commissions it, the
   standards that govern it, its common variants, and what goes wrong in practice.
2. The scenarios practitioners look for that the records can evidence.
3. How accountants perform it: the populations, measures, tests, tolerances and
   evidence standards they use, and the records they request from the client.
4. How accountants report it: the headline figure, the standard exhibits (walks,
   bridges, roll-forwards, schedules), their order and what leads.

State the objective and readers, population definitions, closed lists, evidence
standards, measure definitions, invariants, difference classes and their order,
verdicts, client-policy routing, the headline figure and the deliverable's shape.

State no method: no step order, no item-table recipe, no `params` plumbing beyond the
`*_from` names, and no rule `validate_recipe.py` already enforces. Reduce a useful
method pattern to one Toolbox bullet. Write each rule once, as the general rule. Write
no rule for a single data room.

## Research

Research from your knowledge of the profession's practice. Use no web search or web fetch.
Cover the four areas in § What a recipe states. Draw on:

- Standards and guidance: FASB ASC, PCAOB AS, AICPA AU-C and audit guides, SEC
  guidance, IFRS where relevant. Cite a topic, standard or paragraph only where you are
  certain of the reference; otherwise name the requirement without a citation.
- Practice material from Big 4 and mid-tier firms, transaction-advisory and QoE
  providers, lenders and valuation firms where they are the reader, and FP&A,
  controllership and operations practitioners.
- Enforcement and restatement cases (SEC AAERs, PCAOB inspection findings) for the
  scenarios that go wrong in practice.
- Client request lists (PBC lists, diligence request lists): the records practitioners
  ask for, which become the recipe's source classes.
- Sample deliverables: diligence reports, audit workpapers, board and lender packs, and
  the exhibits, order and terms they use.

Write a research table. Each row is one scenario, measure, test, source record or report
element; the recipe section it goes to; and its basis: the standard it rests on, or the
practice it reflects. Put each item the records cannot evidence in `What the plan notes
rather than checks`.

## Write the recipe

Fix the frame first: the frontmatter `name` (kebab-case, not a name the catalog
carries); the objective, in one sentence; the readers and the scope, with the variants
in and out; the population and the source classes; each option the run needs from the
user, as a `declares` key; the families, each with what it establishes and what it
reads.

Write the sections in this order. Sections `RECIPE_FORMAT.md` requires are marked *.

1. Frontmatter per `RECIPE_FORMAT.md` § The document.
2. Intro: who uses the recipe, the readers, the scope.
3. `Rules`: numbered; each rule opens with its instruction, with no title. Include
   these where they apply: pattern before size; nothing left in prose (an untested
   pattern becomes a proposed hypothesis or a `D.`); claims stated as hypotheses with
   the test fixed before the result.
4. `Population`* with its closed ruling list.
5. A client-policy section where the analysis turns on a client policy. Example: `The ARR
   policy`.
6. `Source classes`*, `Granularity`*, `The period set`.
7. `Measures`: a definition table with the practitioner measures the research found,
   then `Invariants`.
8. Sections specific to the analysis. Examples: `The event register`, `Data quality`.
9. `How issues are reported`: a table of issue → record id prefix → where the reader
   sees it; the fields each record carries; one example sentence of a written issue;
   `Lists`, saying which lists are fixed and which are starting sets the run extends.
10. `Toolbox`: one-line patterns for the inquiry family, each citing the policy or
    decision ids it turns on. The plan registers a line for each pattern the records can
    carry, gives a one-line reason for each it skips, and adds patterns the data shows.
11. `The families`*: open with "Each family states what it establishes, what it reads
    and when it is done. The worker chooses the method and records it." Each family has
    **Establishes:**, **Reads:** (with the `params.*_from` names) and **Done when:**. An
    inquiry family runs one check per line of inquiry and names the lines required on
    every run.
12. `Exec summary`*: what the reader came to learn; what the first page leads with;
    findings in three parts (key finding with its number, the observations with the tab
    each rests on, the consequence with the figure it moves and the owner). Name the
    owner; state no action for the owner or the reader.
13. `Report`*: prose first, then exactly one ```` ```json ```` block. Order the deck the
    way practitioners present this analysis: what the reader came for leads (`place:
    lead`), support goes to the appendix. Head every narrative page with one sentence
    stating its conclusion with its number. End the narrative with `Next steps` and
    `Scope`.
14. `What the plan notes rather than checks`*: route each item to the skill that owns
    it, or to a `D.` or `Q.`.

State acceptance in `Rules`, the invariants and each family's **Done when**.

`validate_recipe.py` does not check these:

- Family letters collide with no decision-id letter of a policy the recipe declares.
  Example: `ARR_POLICY.md` decision ids use A, L, R, S and V.
- Every `§` reference names a section that exists.
- Instructions are imperative and active; no heading reads "X, not Y"; examples are
  labeled "Example:" or "Examples:"; the profession's terms, no coined ones; US spelling.

Then run the gate and fix every defect it names:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_recipe.py <recipe path>
```

## In a run

Arguments: `run_dir`, `seq`, `ask` (the user's ask, verbatim), `catalog` (the served
`catalog.yaml`, so you know what exists and do not re-author it), and, on the author
stage, `answers` (the user's answers to the questions your draft stage returned, verbatim).
Without `answers` you are on the draft stage; with it, the author stage. Append
`step_start` before reading and `step_end` as your last act (`OBSERVABILITY.md`).

Read `run.json`. Its registered sources are the data room; you read them under
`agents/planner.md`'s rules, through `scripts/peek.py`, bounded per
`${CLAUDE_PLUGIN_ROOT}/reference/CONDUCT.md § Reading client files`. You write a recipe, not a plan: no file
index, no profiles, no definition. `check-plan` does that against the recipe you leave.

### Draft stage (no `answers`)

Peek every registered file, a folder in one call, so you know what the data room holds:
which of the three source classes are present, what grain the records carry, what
period they cover. Then write `steps/<NNNN>-recipe.json` per `RUN_CONTRACT.md` with
`outcome: complete`, `produced: []`, and in `notes` the questions, numbered, each one
sentence, that settle the frame (§ Write the recipe):

1. the objective, in one sentence you propose from the ask and they confirm or correct;
2. the population: the statement line and the accounts it is drawn from;
3. the source classes you found, and which class the objective rests on;
4. the grain the data supports for each family you foresee, and where it is coarser
   than the objective needs;
5. whatever the ask leaves open: a period, a standard, a reader, an option a `declares`
   key would carry.

Ask nothing the data room already answers. Return the questions as your last lines; the
relay puts them to the user.

### Author stage (`answers` given)

Research per § Research. Add rows for what the data room shows of the company's own
practice: its policies, management's reporting packs, prior reports and audit
adjustments. Each such row's basis is the file. Write `<run_dir>/recipes/<name>.md` per
§ Write the recipe, with `objective` taken verbatim from the confirmed answer and a
`declares` key for each option the answers left to the user. A defect the gate names
that you cannot clear is `outcome: blocked`, with the gate's output verbatim in
`blockers` and the file deleted; the plan step never receives a recipe the gate refused.

`steps/<NNNN>-recipe.json` names the recipe in `produced` and every client file you
opened in `consumed`. `conclusion` is two sentences: what the recipe establishes, and
how many families over which source classes. `notes` carries the research table, one row
per line.

### Return

At most six lines: the recipe path and its `name`, the family count, the source classes
it expects, the options it declares, and the gate's last line.
