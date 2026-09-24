---
name: create-recipe
description: >-
  Author a playbook recipe for an analysis the catalog does not cover, from the user's
  ask and the registered data room: a draft pass that reads the sources and returns the
  questions the recipe needs answered, then an author pass that writes the recipe to the
  run directory and validates it against the recipe contract.
context: fork
agent: countz-accounting:planner
background: false
user-invocable: false
---

# Author the recipe

Arguments: `run_dir`, `seq`, `ask` (the user's ask, verbatim), `catalog` (the served
`catalog.yaml`, so you know what exists and do not re-author it), and on the author
pass `answers` (the user's answers to the questions your draft pass returned, verbatim).
Without `answers` you are on the draft pass; with it, the author pass. Append
`step_start` before reading and `step_end` as your last act (`OBSERVABILITY.md`).

Read `${CLAUDE_PLUGIN_ROOT}/reference/RECIPE_FORMAT.md` whole — it is the contract you
write to — then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/PLAYBOOK_RECIPES.md "What every recipe inherits"`,
then `run.json`. Its registered sources are the data room; you read them under
`agents/planner.md`'s rules, through `scripts/peek.py`, bounded per
`${CLAUDE_PLUGIN_ROOT}/reference/CONDUCT.md § Reading client files`. You write a recipe, not a plan: no file
index, no profiles, no definition. `check-plan` does that against the recipe you leave.

## Draft pass (no `answers`)

Peek every registered file — a folder in one call — so you know what the room holds:
which of the three source classes are present, what grain the records carry, what
period they cover. Then write `steps/<NNNN>-recipe.json` per `RUN_CONTRACT.md` with
`outcome: complete`, `produced: []`, and in `notes` the questions, numbered, each one
sentence, that the recipe cannot be written without:

1. the objective, in one sentence you propose from the ask and they confirm or correct;
2. the population — the statement line and the accounts it is drawn from;
3. the source classes you found, and which class the objective rests on;
4. the grain the data supports for each family you foresee, and where it is coarser
   than the objective needs;
5. whatever the ask leaves open: a period, a standard, a reader, an option a `declares`
   key would carry.

Ask nothing the room already answers. Return the questions as your last lines; the relay
puts them to the user.

## Author pass (`answers` given)

Write `<run_dir>/recipes/<name>.md`, `name` kebab-case and not a name the catalog
carries. Frontmatter per `RECIPE_FORMAT.md`: `name`, `objective` (from the confirmed
answer, verbatim), `declares` for any option the answers left to the user (and
`arr_policy` whenever the objective computes ARR, recurring-revenue retention, churn or
an ARR bridge: those families read every ARR choice from the policy by decision id,
`${CLAUDE_PLUGIN_ROOT}/reference/ARR_POLICY.md`), `headline`
naming the one-check family whose walk the deliverable leads with, `lead` where more
than one tab follows the Exec Summary. The seven required sections in order, `## Report`
among them: its `metrics.title` is the headline of the deck's key-metrics page — the
measure the deliverable exists to state — and its `schedules` are the tables from the
headline and lead families' tabs a reader of this report type opens it for, each
naming header words the family's section says its tab carries (RECIPE_FORMAT.md
§ Report). Families
composed only from `KINDS` in `${CLAUDE_PLUGIN_ROOT}/scripts/check_playbook.py`,
headed exactly as the contract states, numbered from 0 where family 0 is the population
walk; each says what it establishes, what it reads, and the families before it. Write
in the language of the practitioner who would sign the workbook — the profession's
terms, no coined ones.

Then the gate, whose non-zero exit is yours to fix before you write your record:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_recipe.py <run_dir>/recipes/<name>.md
```

A defect you cannot clear is `outcome: blocked` with the gate's output verbatim in
`blockers` and the file deleted — the plan step never receives a recipe the gate refused.
`steps/<NNNN>-recipe.json` names the recipe in `produced` and every client file you
opened in `consumed`; `conclusion` is two sentences: what the recipe establishes, and
how many families over which source classes.

## Return

At most six lines: the recipe path and its `name`, the family count, the source classes
it expects, the options it declares, and the gate's last line.
