---
name: drilldown
description: >-
  Drill down into a result of a finished run and explain it in accounting terms: what the
  item is, what it rests on, and why it is worth attention. Re-performs the statements
  behind it and queries the run for the evidence around it first. Invoke when the user
  asks to drill into, explain or question a figure, finding or open item of a run, for
  example "drilldown the 1,406 customers first billed in August 2025". A question about an
  accounting concept that names no result of a run is outside this skill. For the
  step-by-step data and SQL, use `reperform`.
argument-hint: "[run directory] the figure, finding or open item"
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do grep -qs '^def emptying' "$d/scripts/sql.py" && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/sql.py" -exec grep -l '^def emptying' {} + 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/sql.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/sql.py" -exec grep -l '^def emptying' {} + 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/sql.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" DOCTRINE.md "Voice" "Number conventions"; fi
```

`$R` below is the `CLAUDE_PLUGIN_ROOT` the block printed. You explain one result from the
run's own tables, in this conversation.

## Inputs

- **The result**: the figure, finding or open item the arguments or the invoking message
  name. Where they name only a concept (example: "ARR", "ASC 606"), answer it in a few
  sentences, then ask which result of the run to drill into.
- **The run directory**: a path in the arguments; else the run this session ran or last
  named; else ask the user for it. It holds `run.json` and `catalog.sql`.

## Querying

Run SQL with `$R/scripts/countz-sql -agent -init <run_dir>/catalog.sql -c "<sql>"`. Each
call starts an empty in-memory database: a `CREATE TEMP VIEW` lasts for that call, so put
the queries that use it in the same `-c`. The catalog describes the run:

- `countz.tables`: every table, with a parsed table's file, sheet and rows, and a derived
  table's statement in `definition`;
- `countz.columns`: each column's type, description and unit;
- `countz.figures`: every figure, with its `statement`; `fig('F.x')` reads one;
- `countz.reads`: what each statement reads (`reader`, `read`);
- `countz.ties`, and `room.constants` with each constant's `kind` (`stated`, `declared`,
  `chosen`) and its `quote` or `basis`.

Compute in SQL. Use Python only for what SQL cannot do. Write nothing into the run:
create no table in a run schema, and call no `run_sql` or `Ledger`.

## 1. Find the result

Search `countz.figures` for the figures the description names, by label, id, and value
within 0.5% of each number the description states (example: `abs(value - 20820000) <=
0.005 * 20820000`). A description quoted from the run's output: grep `out/RUN_SUMMARY.md` and
`checks/*.md` for its numbers to find the check and the ids. Where a table or a tie holds
the result and no figure does, explain that table or tie.

## 2. Re-perform it

Query `SELECT * FROM lineage('<figure id>')`: the statements behind the figure, in the
order a re-performer runs them, down to the parsed tables and the constants. Run the
figure's `statement` against the run's tables and compare its value with the recorded
one. If they differ, report both values and stop. For a figure with no statement (a
tie's difference), re-perform each side.

Read the statements of the nodes the value rests on: `definition` in `countz.tables`,
`statement` in `countz.figures`, and each constant's row in `room.constants`. Where a
statement builds several results (UNION branches, CTEs), follow the branch that yields
the figure's row. A `chosen` constant is the run's judgment; step 3 tests it.

## 3. Fill the gaps

The lineage shows how the run computed the value. Query for what the reader also needs
to understand it. Examples of gaps:

- the evidence for each `chosen` constant (example: a month chosen as unusual, and the
  monthly series that shows whether it is);
- each condition of a filter applied one at a time, and what each removes;
- the population next to a comparison group;
- each plausible explanation, and whether the data supports or rules it out;
- the figures that read this one (`countz.reads` where `read` is its id), and how far
  they move;
- the run's open questions about it (`checks/<check>.md`).

## 4. Explain

Write it for an accountant, in accounting terms: the account, the balance or metric, the
policy rule, the period and the counterparty. Name a table, column or statement only
where the reader needs it to find the record. No SQL.

1. **What the item is.** One paragraph: what the result measures, which records it rests
   on, and which policy rule or judgment puts it there.
2. **Why it is worth attention.** Its size against materiality and against the total it
   is part of (example: the share of ARR at the period end); the figures and pages that
   read it and how far they move; how it would change under the alternative the run
   records for the rule or judgment behind it; and what in the records it leaves
   unexplained. State the condition and its quantified consequence; do not grade the
   risk.
3. **What the records do not show**, and who holds the answer where the run names an owner.

Show the evidence that carries a point in a short table. Mark every figure as the run's,
with its id, or as computed for this explanation and absent from the run's ledger. End
with this line:

> To walk through the data and re-perform each step, say: reperform.

Write the explanation per § Voice and § Number conventions, which the block printed.
