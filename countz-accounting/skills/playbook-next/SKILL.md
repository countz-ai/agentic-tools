---
name: playbook-next
description: >-
  Decide the next wave of a playbook run from the definition and the records on disk, and
  write the dispatch briefs. Returns imperatives; the relay executes them.
context: fork
agent: countz-accounting:playbook-engine
background: false
user-invocable: false
---

# Decide the next wave

Arguments: `run_dir`, `playbook` (absolute path to the definition).

`${CLAUDE_PLUGIN_ROOT}/scripts/playbook_next.py` makes this decision whenever it is a
pure function of disk — the relay runs it first, always. You are invoked when it printed
`ESCALATE: <reason>` — read that reason before anything else. It wrote nothing when it
escalated, so the decision is entirely yours: redo it whole, from disk, by the procedure
below, then return; the relay goes back to the script for the next one. A divergence
between the script and this procedure is a bug in the script.

You read JSON and records, and you write briefs and one decision event; the relay
executes what you return.

## Procedure

1. Validate the definition:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_playbook.py <playbook>`. On a non-zero
   exit, return the error instead of a decision — a broken definition is reported, not
   worked around.
2. Read `run.json` — the binding (`playbook.bound`), the sources, `next_seq`, and the
   dispatches — and the step records under `steps/` for the playbook's steps. Fold: classify
   from the record, `error` before `outcome` — except a record claiming `blocked` with
   a non-empty `blockers`, which is blocked whatever `error` carries (RUN_CONTRACT.md
   § Classification and retries); a record that is absent or unparseable takes the row's terminal
   `state`.
3. Decide per `${CLAUDE_PLUGIN_ROOT}/reference/PLAYBOOKS.md`:
   - a step whose `after` dependencies are all terminal ok-or-blocked, whose sources are
     all bound, and which has no terminal dispatch — goes in this wave. All such steps
     go in this one decision.
   - a step whose dependency failed, or whose slot the user left unbound, is skipped with
     the reason; the run continues degraded.
   - every step terminal or skipped — DONE.
4. For a wave: resolve each step's kind to its skill through `KINDS` in
   `${CLAUDE_PLUGIN_ROOT}/scripts/check_playbook.py`, map its slots to the bound source
   ids, take seqs from `next_seq` upward, and write one brief per step at
   `dispatch/<NNNN>-<step>.md`, rendering the `BRIEF` template in
   `${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py` verbatim — absolute paths, complete
   arguments, the step's `goal` and `params` carried verbatim.
5. Append the `decision` event (`OBSERVABILITY.md`) — `why` states the comparison that
   decided it, which records exist and which dependencies are terminal, not a
   restatement of the rule — then return.

## Return

The same imperatives the script prints:

```
playbook <name>  wave=<n>  <k> dispatch(es)
<the comparison that decided it, one sentence>
SAY: Wave <n> — running <k> checks in parallel: <what runs>.
RECORD: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py dispatch <abs run_dir> --briefs <abs brief paths>
LAUNCH: <the LAUNCH constant in ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py, verbatim>
NEXT: Skill check-tie run_dir=<abs> seq=<n> check=<step id> sources=<ids> goal=<...> mode=fresh brief=<abs brief path>
THEN: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py record <abs run_dir>
THEN: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/playbook_next.py <abs run_dir> <abs definition path>
```

The `SAY:` line is the relay's progress line to the user (`RUN_CONTRACT.md` § Every
wave); a wave of one reads `running 1 check:`. `<what runs>` is
`describe_members` in `${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py`, rendered the same:
each recipe family the members cover as `<ID> <title>` from its `###` header
(`run.json.plan.recipe`), counted `<n> × ` where more than one; a member with no recipe
family as `<id> (<kind word>)` from `KIND_WORDS`.

One `NEXT:` line per wave member; a step this decision skips is a `SKIPPED: <step> —
<reason>` line; the `THEN:` lines close the wave and send the relay back to the script
for the next decision. On DONE: `DONE:` with one line per step that ended blocked,
failed or skipped (no `RECORD:`, `LAUNCH:` or `THEN:` — the run moves to the
review-and-report
tail), so the relay can put it to the user. Never return step output or a summary of the
run.
